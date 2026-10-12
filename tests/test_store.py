import base64
import hashlib
import sqlite3
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from backup import create_backup
from agri_vision.config import Settings, validate_runtime_security
from agri_vision.inference import InferenceResult
from agri_vision.store import Store, image_dimensions
from restore import restore_backup


def png_fixture(width: int = 1280, height: int = 720, suffix: bytes = b"fixture") -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00" + suffix


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.store = Store(str(root / "db.sqlite3"), str(root / "media"))
        self.farm = self.store.create_farm("Fazenda teste", "SP")
        self.plot = self.store.create_plot(
            self.farm["id"],
            "Talhão A",
            "café",
            {"min_lat": -23.1, "min_lon": -47.1, "max_lat": -23.0, "max_lon": -47.0},
        )
        self.campaign = self.store.create_campaign(self.plot["id"], "v1", "2026-10", "contagem de frutos")

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_existing_database_is_migrated_without_losing_records(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE farms (id TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE plots (id TEXT PRIMARY KEY, farm_id TEXT NOT NULL, name TEXT NOT NULL, crop TEXT NOT NULL, min_lat REAL, min_lon REAL, max_lat REAL, max_lon REAL, created_at TEXT NOT NULL);
            CREATE TABLE campaigns (id TEXT PRIMARY KEY, plot_id TEXT NOT NULL, protocol_version TEXT NOT NULL, captured_period TEXT NOT NULL, task TEXT NOT NULL, created_at TEXT NOT NULL);
            INSERT INTO farms VALUES ('legacy-farm', 'Fazenda antiga', 'SP', '2026-01-01T00:00:00+00:00');
            """
        )
        connection.commit()
        connection.close()

        migrated = Store(str(legacy_path), str(Path(self.temp_dir.name) / "legacy-media"))
        farm = migrated.connection.execute("SELECT * FROM farms WHERE id = 'legacy-farm'").fetchone()
        farm_columns = {row["name"] for row in migrated.connection.execute("PRAGMA table_info(farms)")}
        campaign_columns = {row["name"] for row in migrated.connection.execute("PRAGMA table_info(campaigns)")}
        index_names = {row["name"] for row in migrated.connection.execute("PRAGMA index_list(campaigns)")}
        version = migrated.connection.execute("PRAGMA user_version").fetchone()[0]
        migrated.close()
        self.assertEqual(farm["name"], "Fazenda antiga")
        self.assertIn("organization_id", farm_columns)
        self.assertIn("status", campaign_columns)
        self.assertIn("idx_campaigns_plot_status", index_names)
        self.assertEqual(version, 1)

    def test_quality_rejects_out_of_domain_and_duplicate_sync_is_idempotent(self) -> None:
        event = {
            "client_event_id": "device-1:1",
            "content_hash": "abc",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "soja", "latitude": -23.05, "longitude": -47.05},
        }
        first = self.store.add_sample(self.campaign["id"], event)
        second = self.store.add_sample(self.campaign["id"], event)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["quality_status"], "out_of_domain")
        conflicting = dict(event, content_hash="different")
        with self.assertRaisesRegex(ValueError, "client_event_conflict"):
            self.store.add_sample(self.campaign["id"], conflicting)

    def test_review_is_traceable_and_report_does_not_extrapolate(self) -> None:
        event = {
            "client_event_id": "device-1:2",
            "content_hash": "def",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        self.store.review_observation(sample["observation_id"], 12, "Conferido pelo agrônomo", "ana")
        self.store.review_observation(sample["observation_id"], 13, "Revisão corrigida", "ana")
        report = self.store.report(self.plot["id"])
        self.assertEqual(report["campaigns"][0]["reviewed_count"], 1)
        reviews = self.store.list_observation_reviews(sample["observation_id"])
        self.assertEqual([review["version"] for review in reviews], [1, 2])
        self.assertEqual(reviews[-1]["prediction"], 13)
        self.assertFalse(report["extrapolation_allowed"])
        review_events = [event for event in self.store.list_audit_events("default") if event["action"] == "reviewed"]
        self.assertEqual(review_events[-1]["actor"], "ana")
        self.assertEqual(review_events[-1]["entity_id"], sample["observation_id"])

    def test_inference_contract_keeps_unconfigured_model_pending(self) -> None:
        event = {
            "client_event_id": "device-1:3",
            "content_hash": "ghi",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        self.store.add_sample(self.campaign["id"], event)
        results = self.store.run_inference(self.campaign["id"])
        self.assertEqual(results[0]["status"], "pending_model")
        self.assertIsNone(results[0]["prediction"])

    def test_inference_blocks_engine_without_validated_registry_entry(self) -> None:
        event = {
            "client_event_id": "device-1:unvalidated",
            "content_hash": "unvalidated-hash",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        self.store.add_sample(self.campaign["id"], event)

        class UnvalidatedEngine:
            model_version = "not-registered"

            def infer(self, media_path, metadata, task):
                return InferenceResult(999, 1.0, self.model_version, "predicted")

        result = self.store.run_inference(self.campaign["id"], UnvalidatedEngine())[0]
        self.assertEqual(result["status"], "model_not_validated")
        self.assertIsNone(result.get("prediction"))

    def test_missing_location_stays_pending_instead_of_being_assigned_to_a_plot(self) -> None:
        event = {
            "client_event_id": "device-1:4",
            "content_hash": "jkl",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café"},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        self.assertEqual(sample["quality_status"], "pending_location")
        self.assertIn("location_missing", sample["quality_reasons"])

    def test_organization_scope_blocks_cross_tenant_access(self) -> None:
        other_farm = self.store.create_farm("Outra fazenda", "MG", "org-b")
        with self.assertRaisesRegex(ValueError, "farm_not_found_or_forbidden"):
            self.store.create_plot(other_farm["id"], "Talhão bloqueado", "café", None, "org-a")
        event = {
            "client_event_id": "device-org-a:1",
            "content_hash": "mno",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event, "default")
        with self.assertRaisesRegex(ValueError, "observation_not_found_or_forbidden"):
            self.store.review_observation(sample["observation_id"], 3, "não autorizado", "outro", "org-b")

    def test_dataset_version_requires_explicit_split_and_is_scoped(self) -> None:
        with self.assertRaisesRegex(ValueError, "split_definition_requires_group_by"):
            self.store.create_dataset_version("sem split", "celular", "piloto", {}, "default")
        version = self.store.create_dataset_version(
            "cafe-2026-v1",
            "capturas autorizadas da campanha 2026-10",
            "uso interno do piloto",
            {"group_by": "property", "evaluation": "fazenda-reserva"},
            "org-a",
        )
        self.assertEqual(version["split_definition"]["group_by"], "property")
        self.assertEqual(len(self.store.list_dataset_versions("org-a")), 1)
        self.assertEqual(self.store.list_dataset_versions("org-b"), [])

    def test_backup_contains_consistent_database_snapshot_and_media(self) -> None:
        root = Path(self.temp_dir.name)
        backup_path = root / "backups" / "snapshot.zip"
        created = create_backup(str(root / "db.sqlite3"), str(root / "media"), str(backup_path))
        with zipfile.ZipFile(created) as archive:
            self.assertIn("agri_vision.sqlite3", archive.namelist())
        restored = root / "restored"
        restore_backup(str(created), str(restored))
        self.assertTrue((restored / "agri_vision.sqlite3").exists())

        tampered = root / "backups" / "tampered.zip"
        with zipfile.ZipFile(created) as source, zipfile.ZipFile(tampered, "w") as target:
            for member in source.infolist():
                data = source.read(member.filename)
                if member.filename == "agri_vision.sqlite3":
                    data += b"tampered"
                target.writestr(member, data)
        with self.assertRaisesRegex(ValueError, "backup_integrity_mismatch:agri_vision.sqlite3"):
            restore_backup(str(tampered), str(root / "tampered-restore"))

        extra = root / "backups" / "extra-file.zip"
        with zipfile.ZipFile(created) as source, zipfile.ZipFile(extra, "w") as target:
            for member in source.infolist():
                target.writestr(member, source.read(member.filename))
            target.writestr("unexpected.txt", b"not declared")
        with self.assertRaisesRegex(ValueError, "backup_manifest_members_mismatch"):
            restore_backup(str(extra), str(root / "extra-restore"))

    def test_environment_settings_are_overridable(self) -> None:
        settings = Settings("127.0.0.1", 8765, "db.sqlite3", "media")
        self.assertEqual(settings.port, 8765)
        if self.store.database != ":memory:":
            journal_mode = self.store.connection.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")

    def test_public_bind_requires_api_key(self) -> None:
        validate_runtime_security("127.0.0.1", None)
        validate_runtime_security("localhost", None)
        validate_runtime_security("0.0.0.0", "secret")
        with self.assertRaisesRegex(ValueError, "api_key_required_for_non_loopback_host"):
            validate_runtime_security("0.0.0.0", None)

    def test_uploaded_media_hash_is_verified(self) -> None:
        media = png_fixture(suffix=b"fixture-image-bytes")
        event = {
            "client_event_id": "device-1:media",
            "content_hash": hashlib.sha256(media).hexdigest(),
            "media_base64": base64.b64encode(media).decode(),
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        self.assertTrue(Path(sample["media_path"]).exists())
        event["client_event_id"] = "device-1:media-dimension-mismatch"
        event["content_hash"] = hashlib.sha256(media).hexdigest()
        event["capture_metadata"] = dict(event["capture_metadata"], width=640)
        with self.assertRaisesRegex(ValueError, "image_dimensions_mismatch"):
            self.store.add_sample(self.campaign["id"], event)
        event["client_event_id"] = "device-1:media-bad"
        event["content_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "content_hash_mismatch"):
            self.store.add_sample(self.campaign["id"], event)

    def test_upload_rejects_non_image_media(self) -> None:
        media = b"not-an-image"
        event = {
            "client_event_id": "device-1:non-image",
            "content_hash": hashlib.sha256(media).hexdigest(),
            "media_base64": base64.b64encode(media).decode(),
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        with self.assertRaisesRegex(ValueError, "unsupported_media_type"):
            self.store.add_sample(self.campaign["id"], event)

    def test_webp_dimensions_are_read_from_image_header(self) -> None:
        media = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 4 + b"\x00" * 4 + (1279).to_bytes(3, "little") + (719).to_bytes(3, "little")
        self.assertEqual(image_dimensions(media), (1280, 720))

    def test_campaign_evaluation_reports_error_and_coverage_against_review(self) -> None:
        event = {
            "client_event_id": "device-1:evaluation",
            "content_hash": "pqr",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event)

        class FixedEngine:
            model_version = "test-model-1"

            def infer(self, media_path, metadata, task):
                return InferenceResult(10, 0.8, self.model_version, "needs_review")

        dataset = self.store.create_dataset_version(
            "dataset-evaluation",
            "protocolo-v1",
            "consentimento-v1",
            {"group_by": "property", "evaluation_groups": ["fazenda-reserva"]},
        )
        self.store.create_model_version(
            "test-model-1",
            "contagem de frutos",
            "c" * 64,
            dataset["id"],
            "validated",
        )
        self.store.run_inference(self.campaign["id"], FixedEngine())
        self.store.review_observation(sample["observation_id"], 12, "referência humana", "ana")
        evaluation = self.store.evaluate_campaign(self.campaign["id"])
        self.assertEqual(evaluation["status"], "evaluated")
        self.assertEqual(evaluation["evaluated_count"], 1)
        self.assertEqual(evaluation["mae"], 2)
        self.assertAlmostEqual(evaluation["median_relative_error"], 1 / 6)
        self.assertEqual(evaluation["error_by_reference_range"]["10-49"]["sample_count"], 1)
        self.assertEqual(evaluation["error_by_reference_range"]["10-49"]["mae"], 2)

    def test_retention_defaults_to_preview_and_execute_removes_media_and_sample(self) -> None:
        media = png_fixture(suffix=b"retention-media")
        event = {
            "client_event_id": "device-1:retention",
            "content_hash": hashlib.sha256(media).hexdigest(),
            "media_base64": base64.b64encode(media).decode(),
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        preview = self.store.purge_samples_before("9999-01-01T00:00:00+00:00")
        self.assertFalse(preview["execute"])
        self.assertEqual(preview["sample_count"], 1)
        removed = self.store.purge_samples_before("9999-01-01T00:00:00+00:00", execute=True, actor="retention-test")
        self.assertEqual(removed["sample_count"], 1)
        with self.assertRaisesRegex(ValueError, "sample_not_found"):
            self.store.sample_with_observation(sample["id"])

    def test_invalid_capture_metadata_is_rejected_explicitly(self) -> None:
        event = {
            "client_event_id": "device-1:invalid-metadata",
            "content_hash": "stu",
            "capture_metadata": {"width": "1280", "height": 720, "blur_score": 0.9, "crop": "café"},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        self.assertEqual(sample["quality_status"], "rejected")
        self.assertEqual(sample["quality_reasons"], ["metadata_invalid"])

    def test_model_registry_requires_provenance_for_validated_models(self) -> None:
        with self.assertRaisesRegex(ValueError, "validated_model_requires_dataset"):
            self.store.create_model_version("model-1", "contagem de frutos", "a" * 64, None, "validated")
        incomplete_dataset = self.store.create_dataset_version("dataset-incomplete", "capturas do piloto", "uso interno", {"group_by": "property"})
        with self.assertRaisesRegex(ValueError, "validated_model_requires_complete_dataset"):
            self.store.create_model_version("model-incomplete", "contagem de frutos", "b" * 64, incomplete_dataset["id"], "validated")
        dataset = self.store.create_dataset_version("dataset-1", "capturas do piloto", "uso interno", {"group_by": "property", "evaluation_groups": ["farm-reserve"]})
        model = self.store.create_model_version("model-1", "contagem de frutos", "A" * 64, dataset["id"], "validated", "default", "ana")
        self.assertEqual(model["artifact_sha256"], "a" * 64)
        self.assertEqual(self.store.list_model_versions()[0]["status"], "validated")

    def test_campaign_transitions_are_ordered_and_audited(self) -> None:
        campaign = self.store.transition_campaign(self.campaign["id"], "collecting", "default", "ana")
        self.assertEqual(campaign["status"], "collecting")
        campaign = self.store.transition_campaign(self.campaign["id"], "review", "default", "ana")
        self.assertEqual(campaign["status"], "review")
        with self.assertRaisesRegex(ValueError, "campaign_transition_not_allowed"):
            self.store.transition_campaign(self.campaign["id"], "draft")
        events = [event for event in self.store.list_audit_events() if event["action"] == "transitioned"]
        self.assertEqual(len(events), 2)

    def test_campaign_state_blocks_new_samples_after_collection(self) -> None:
        event = {"client_event_id": "state-sample-1", "content_hash": "state-hash", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05}}
        self.store.transition_campaign(self.campaign["id"], "collecting")
        self.store.add_sample(self.campaign["id"], event)
        self.store.transition_campaign(self.campaign["id"], "review")
        with self.assertRaisesRegex(ValueError, "campaign_not_collecting"):
            self.store.add_sample(self.campaign["id"], dict(event, client_event_id="state-sample-2"))

    def test_dataset_export_requires_evaluation_groups_and_excludes_rejected_samples(self) -> None:
        accepted = self.store.add_sample(self.campaign["id"], {"client_event_id": "export-accepted", "content_hash": "123", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05}})
        self.store.add_sample(self.campaign["id"], {"client_event_id": "export-rejected", "content_hash": "456", "capture_metadata": {"width": 320, "height": 240, "blur_score": 0.1, "crop": "café", "latitude": -23.05, "longitude": -47.05}})
        incomplete = self.store.create_dataset_version("incomplete", "pilot", "internal", {"group_by": "property"})
        with self.assertRaisesRegex(ValueError, "split_definition_requires_evaluation_groups"):
            self.store.export_dataset(incomplete["id"])
        complete = self.store.create_dataset_version("complete", "pilot", "internal", {"group_by": "property", "evaluation_groups": [self.plot["farm_id"]]})
        exported = self.store.export_dataset(complete["id"])
        self.assertEqual([item["sample_id"] for item in exported], [accepted["id"]])
        self.assertEqual(exported[0]["split"], "evaluation")

    def test_report_compares_campaign_means_without_extrapolating(self) -> None:
        first_event = {
            "client_event_id": "device-1:trend-1",
            "content_hash": "vwx",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        first = self.store.add_sample(self.campaign["id"], first_event)
        self.store.review_observation(first["observation_id"], 10, "primeira campanha", "ana")
        second_campaign = self.store.create_campaign(self.plot["id"], "v1", "2026-11", "contagem de frutos")
        second_event = dict(first_event, client_event_id="device-1:trend-2")
        second = self.store.add_sample(second_campaign["id"], second_event)
        self.store.review_observation(second["observation_id"], 13, "segunda campanha", "ana")
        report = self.store.report(self.plot["id"])
        self.assertEqual(report["campaigns"][1]["delta_from_previous"], 3)
        self.assertFalse(report["extrapolation_allowed"])

    def test_coverage_counts_locations_without_extrapolating(self) -> None:
        located = self.store.add_sample(self.campaign["id"], {"client_event_id": "coverage-located", "content_hash": "coverage-a", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05}})
        self.store.add_sample(self.campaign["id"], {"client_event_id": "coverage-missing", "content_hash": "coverage-b", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café"}})
        coverage = self.store.coverage(self.plot["id"])
        self.assertEqual(coverage["sample_count"], 2)
        self.assertEqual(coverage["located_count"], 1)
        self.assertEqual(coverage["pending_location_count"], 1)
        self.assertEqual(coverage["points"][0]["sample_id"], located["id"])
        self.assertFalse(coverage["extrapolation_allowed"])

    def test_invalid_quality_review_is_not_used_as_agronomic_evidence(self) -> None:
        event = {
            "client_event_id": "device-1:invalid-review",
            "content_hash": "yz0",
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "soja", "latitude": -23.05, "longitude": -47.05},
        }
        sample = self.store.add_sample(self.campaign["id"], event)
        self.store.review_observation(sample["observation_id"], 99, "fora do domínio", "ana")
        report = self.store.report(self.plot["id"])
        self.assertEqual(report["campaigns"][0]["reviewed_count"], 0)
        self.assertIsNone(report["campaigns"][0]["reviewed_mean"])


if __name__ == "__main__":
    unittest.main()
