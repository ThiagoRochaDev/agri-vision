from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import statistics
import re
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .inference import InferenceEngine, PendingInferenceEngine

MAX_MEDIA_BYTES = 6 * 1024 * 1024
SCHEMA_VERSION = 1


def is_supported_image(media: bytes) -> bool:
    return media.startswith(b"\xFF\xD8\xFF") or media.startswith(b"\x89PNG\r\n\x1a\n") or (media.startswith(b"RIFF") and media[8:12] == b"WEBP")


def image_dimensions(media: bytes) -> tuple[int, int] | None:
    if media.startswith(b"\x89PNG\r\n\x1a\n") and len(media) >= 24:
        return struct.unpack(">II", media[16:24])
    if media.startswith(b"RIFF") and media[8:12] == b"WEBP" and len(media) >= 30:
        if media[12:16] == b"VP8X":
            width = 1 + int.from_bytes(media[24:27], "little")
            height = 1 + int.from_bytes(media[27:30], "little")
            return width, height
        if media[12:16] == b"VP8 " and len(media) >= 30 and media[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(media[26:28], "little"), int.from_bytes(media[28:30], "little")
    if media.startswith(b"\xFF\xD8\xFF"):
        offset = 2
        while offset + 9 < len(media):
            while offset < len(media) and media[offset] != 0xFF:
                offset += 1
            while offset < len(media) and media[offset] == 0xFF:
                offset += 1
            if offset >= len(media):
                break
            marker = media[offset]
            offset += 1
            if marker in (0xD8, 0xD9):
                continue
            if offset + 2 > len(media):
                break
            segment_length = int.from_bytes(media[offset:offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(media):
                break
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
                if segment_length >= 7:
                    return int.from_bytes(media[offset + 5:offset + 7], "big"), int.from_bytes(media[offset + 3:offset + 5], "big")
            offset += segment_length
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, database: str = "agri_vision.sqlite3", media_dir: str = "media") -> None:
        self.database = database
        self.media_dir = Path(media_dir)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        if database != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def is_ready(self) -> bool:
        try:
            self.connection.execute("SELECT 1").fetchone()
            return self.media_dir.is_dir() and os.access(self.media_dir, os.W_OK)
        except sqlite3.Error:
            return False

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS farms (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL DEFAULT 'default',
                name TEXT NOT NULL,
                region TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plots (
                id TEXT PRIMARY KEY,
                farm_id TEXT NOT NULL REFERENCES farms(id),
                name TEXT NOT NULL,
                crop TEXT NOT NULL,
                min_lat REAL,
                min_lon REAL,
                max_lat REAL,
                max_lon REAL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                plot_id TEXT NOT NULL REFERENCES plots(id),
                protocol_version TEXT NOT NULL,
                captured_period TEXT NOT NULL,
                task TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                client_event_id TEXT NOT NULL UNIQUE,
                content_hash TEXT NOT NULL,
                capture_metadata TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                quality_reasons TEXT NOT NULL,
                media_path TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                sample_id TEXT NOT NULL UNIQUE REFERENCES samples(id),
                prediction REAL,
                confidence REAL NOT NULL,
                model_version TEXT NOT NULL,
                review_status TEXT NOT NULL,
                reviewed_prediction REAL,
                review_note TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                name TEXT NOT NULL,
                provenance TEXT NOT NULL,
                consent_scope TEXT NOT NULL,
                split_definition TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observation_reviews (
                id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL REFERENCES observations(id),
                organization_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                prediction REAL NOT NULL,
                note TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                UNIQUE(observation_id, version)
            );
            CREATE TABLE IF NOT EXISTS model_versions (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                version TEXT NOT NULL,
                task TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                dataset_version_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(organization_id, version)
            );
            """
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(farms)")}
        if "organization_id" not in columns:
            self.connection.execute("ALTER TABLE farms ADD COLUMN organization_id TEXT NOT NULL DEFAULT 'default'")
        campaign_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(campaigns)")}
        if "status" not in campaign_columns:
            self.connection.execute("ALTER TABLE campaigns ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'")
        current_version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version < 1:
            self.connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_farms_organization ON farms(organization_id);
                CREATE INDEX IF NOT EXISTS idx_plots_farm ON plots(farm_id);
                CREATE INDEX IF NOT EXISTS idx_campaigns_plot_status ON campaigns(plot_id, status);
                CREATE INDEX IF NOT EXISTS idx_samples_campaign_event ON samples(campaign_id, client_event_id);
                CREATE INDEX IF NOT EXISTS idx_audit_organization_created ON audit_events(organization_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_models_organization_status ON model_versions(organization_id, status, version);
                PRAGMA user_version = 1;
                """
            )
        self.connection.commit()

    def _new_id(self) -> str:
        return str(uuid.uuid4())

    def _audit(self, organization_id: str, actor: str, action: str, entity_type: str, entity_id: str, metadata: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO audit_events (id, organization_id, actor, action, entity_type, entity_id, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self._new_id(), organization_id, actor, action, entity_type, entity_id, json.dumps(metadata or {}, sort_keys=True), utc_now()),
        )

    def list_audit_events(self, organization_id: str = "default") -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM audit_events WHERE organization_id = ? ORDER BY created_at", (organization_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            result.append(item)
        return result

    def purge_samples_before(self, cutoff: str, organization_id: str = "default", execute: bool = False, actor: str = "system") -> dict[str, Any]:
        rows = self.connection.execute(
            "SELECT s.id, s.media_path FROM samples s JOIN campaigns c ON c.id = s.campaign_id JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE s.created_at < ? AND f.organization_id = ?",
            (cutoff, organization_id),
        ).fetchall()
        sample_ids = [row["id"] for row in rows]
        if not execute:
            return {"execute": False, "sample_count": len(sample_ids), "media_count": sum(row["media_path"] is not None for row in rows)}
        for row in rows:
            self.connection.execute("DELETE FROM observation_reviews WHERE observation_id IN (SELECT id FROM observations WHERE sample_id = ?)", (row["id"],))
            self.connection.execute("DELETE FROM observations WHERE sample_id = ?", (row["id"],))
            self.connection.execute("DELETE FROM samples WHERE id = ?", (row["id"],))
            if row["media_path"]:
                media_path = Path(row["media_path"])
                if media_path.exists():
                    media_path.unlink()
        self._audit(organization_id, actor, "purged", "samples", organization_id, {"cutoff": cutoff, "sample_count": len(sample_ids)})
        self.connection.commit()
        return {"execute": True, "sample_count": len(sample_ids), "media_count": sum(row["media_path"] is not None for row in rows)}

    def create_farm(self, name: str, region: str, organization_id: str = "default", actor: str = "system") -> dict[str, Any]:
        record = {"id": self._new_id(), "organization_id": organization_id, "name": name, "region": region, "created_at": utc_now()}
        self.connection.execute("INSERT INTO farms (id, organization_id, name, region, created_at) VALUES (:id, :organization_id, :name, :region, :created_at)", record)
        self._audit(organization_id, actor, "created", "farm", record["id"], {"region": region})
        self.connection.commit()
        return record

    def create_dataset_version(
        self,
        name: str,
        provenance: str,
        consent_scope: str,
        split_definition: dict[str, Any],
        organization_id: str = "default",
        actor: str = "system",
    ) -> dict[str, Any]:
        if not isinstance(split_definition, dict) or not split_definition.get("group_by"):
            raise ValueError("split_definition_requires_group_by")
        if split_definition["group_by"] not in {"property", "time", "campaign"}:
            raise ValueError("split_group_not_supported")
        record = {
            "id": self._new_id(),
            "organization_id": organization_id,
            "name": name,
            "provenance": provenance,
            "consent_scope": consent_scope,
            "split_definition": json.dumps(split_definition, sort_keys=True),
            "created_at": utc_now(),
        }
        self.connection.execute(
            "INSERT INTO dataset_versions (id, organization_id, name, provenance, consent_scope, split_definition, created_at) VALUES (:id, :organization_id, :name, :provenance, :consent_scope, :split_definition, :created_at)",
            record,
        )
        self._audit(organization_id, actor, "created", "dataset_version", record["id"], {"group_by": split_definition["group_by"]})
        self.connection.commit()
        result = dict(record)
        result["split_definition"] = split_definition
        return result

    def list_dataset_versions(self, organization_id: str = "default") -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM dataset_versions WHERE organization_id = ? ORDER BY created_at",
            (organization_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["split_definition"] = json.loads(item["split_definition"])
            result.append(item)
        return result

    def create_model_version(self, version: str, task: str, artifact_sha256: str, dataset_version_id: str | None, status: str = "candidate", organization_id: str = "default", actor: str = "system") -> dict[str, Any]:
        if status not in {"candidate", "validated", "retired"}:
            raise ValueError("model_status_not_supported")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", artifact_sha256):
            raise ValueError("artifact_sha256_invalid")
        if status == "validated" and not dataset_version_id:
            raise ValueError("validated_model_requires_dataset")
        if dataset_version_id and not self.connection.execute("SELECT 1 FROM dataset_versions WHERE id = ? AND organization_id = ?", (dataset_version_id, organization_id)).fetchone():
            raise ValueError("dataset_version_not_found_or_forbidden")
        if status == "validated":
            dataset = self.connection.execute("SELECT split_definition FROM dataset_versions WHERE id = ? AND organization_id = ?", (dataset_version_id, organization_id)).fetchone()
            split_definition = json.loads(dataset["split_definition"])
            if not split_definition.get("evaluation_groups"):
                raise ValueError("validated_model_requires_complete_dataset")
        record = {"id": self._new_id(), "organization_id": organization_id, "version": version, "task": task, "artifact_sha256": artifact_sha256.lower(), "dataset_version_id": dataset_version_id, "status": status, "created_at": utc_now()}
        self.connection.execute("INSERT INTO model_versions (id, organization_id, version, task, artifact_sha256, dataset_version_id, status, created_at) VALUES (:id, :organization_id, :version, :task, :artifact_sha256, :dataset_version_id, :status, :created_at)", record)
        self._audit(organization_id, actor, "registered", "model_version", record["id"], {"version": version, "status": status, "task": task})
        self.connection.commit()
        return record

    def list_model_versions(self, organization_id: str = "default") -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM model_versions WHERE organization_id = ? ORDER BY created_at", (organization_id,)).fetchall()
        return [dict(row) for row in rows]

    def export_dataset(self, dataset_version_id: str, organization_id: str = "default") -> list[dict[str, Any]]:
        dataset = self.connection.execute("SELECT * FROM dataset_versions WHERE id = ? AND organization_id = ?", (dataset_version_id, organization_id)).fetchone()
        if not dataset:
            raise ValueError("dataset_version_not_found_or_forbidden")
        split = json.loads(dataset["split_definition"])
        evaluation_groups = split.get("evaluation_groups")
        if not isinstance(evaluation_groups, list) or not evaluation_groups:
            raise ValueError("split_definition_requires_evaluation_groups")
        group_by = split["group_by"]
        rows = self.connection.execute(
            "SELECT s.id AS sample_id, s.media_path, s.content_hash, s.capture_metadata, c.id AS campaign_id, c.captured_period, p.farm_id FROM samples s JOIN campaigns c ON c.id = s.campaign_id JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE f.organization_id = ? AND s.quality_status = 'accepted' ORDER BY s.created_at",
            (organization_id,),
        ).fetchall()
        exported = []
        for row in rows:
            group = {"property": row["farm_id"], "campaign": row["campaign_id"], "time": row["captured_period"]}[group_by]
            item = dict(row)
            item["capture_metadata"] = json.loads(item["capture_metadata"])
            item["group"] = group
            item["split"] = "evaluation" if group in evaluation_groups else "train"
            item["dataset_version_id"] = dataset_version_id
            exported.append(item)
        return exported

    def create_plot(self, farm_id: str, name: str, crop: str, geometry: dict[str, float] | None, organization_id: str = "default", actor: str = "system") -> dict[str, Any]:
        if not self.connection.execute("SELECT 1 FROM farms WHERE id = ? AND organization_id = ?", (farm_id, organization_id)).fetchone():
            raise ValueError("farm_not_found_or_forbidden")
        geometry = geometry or {}
        record = {
            "id": self._new_id(),
            "farm_id": farm_id,
            "name": name,
            "crop": crop,
            "min_lat": geometry.get("min_lat"),
            "min_lon": geometry.get("min_lon"),
            "max_lat": geometry.get("max_lat"),
            "max_lon": geometry.get("max_lon"),
            "created_at": utc_now(),
        }
        self.connection.execute(
            "INSERT INTO plots VALUES (:id, :farm_id, :name, :crop, :min_lat, :min_lon, :max_lat, :max_lon, :created_at)",
            record,
        )
        self._audit(organization_id, actor, "created", "plot", record["id"], {"crop": crop})
        self.connection.commit()
        return record

    def create_campaign(self, plot_id: str, protocol_version: str, captured_period: str, task: str, organization_id: str = "default", actor: str = "system") -> dict[str, Any]:
        plot = self.connection.execute("SELECT p.* FROM plots p JOIN farms f ON f.id = p.farm_id WHERE p.id = ? AND f.organization_id = ?", (plot_id, organization_id)).fetchone()
        if not plot:
            raise ValueError("plot_not_found_or_forbidden")
        record = {
            "id": self._new_id(),
            "plot_id": plot_id,
            "protocol_version": protocol_version,
            "captured_period": captured_period,
            "task": task,
            "created_at": utc_now(),
        }
        record["status"] = "draft"
        self.connection.execute("INSERT INTO campaigns (id, plot_id, protocol_version, captured_period, task, status, created_at) VALUES (:id, :plot_id, :protocol_version, :captured_period, :task, :status, :created_at)", record)
        self._audit(organization_id, actor, "created", "campaign", record["id"], {"task": task, "protocol_version": protocol_version})
        self.connection.commit()
        return record

    def transition_campaign(self, campaign_id: str, status: str, organization_id: str = "default", actor: str = "system") -> dict[str, Any]:
        allowed = {"draft", "collecting", "review", "closed", "paused"}
        if status not in allowed:
            raise ValueError("campaign_status_not_supported")
        campaign = self.get_campaign(campaign_id, organization_id)
        if not campaign:
            raise ValueError("campaign_not_found_or_forbidden")
        current = campaign["status"]
        valid_transitions = {
            "draft": {"collecting", "paused"},
            "collecting": {"review", "paused"},
            "review": {"closed", "paused"},
            "paused": {"draft", "collecting"},
            "closed": set(),
        }
        if status not in valid_transitions[current]:
            raise ValueError("campaign_transition_not_allowed")
        self.connection.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))
        self._audit(organization_id, actor, "transitioned", "campaign", campaign_id, {"from": current, "to": status})
        self.connection.commit()
        result = dict(campaign)
        result["status"] = status
        return result

    def get_campaign(self, campaign_id: str, organization_id: str | None = None) -> sqlite3.Row | None:
        scope = " AND f.organization_id = ?" if organization_id is not None else ""
        parameters = (campaign_id, organization_id) if organization_id is not None else (campaign_id,)
        return self.connection.execute(
            "SELECT c.*, p.crop, p.min_lat, p.min_lon, p.max_lat, p.max_lon FROM campaigns c JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE c.id = ?" + scope,
            parameters,
        ).fetchone()

    def add_sample(self, campaign_id: str, event: dict[str, Any], organization_id: str = "default", actor: str = "device") -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id, organization_id)
        if not campaign:
            raise ValueError("campaign_not_found_or_forbidden")
        existing = self.connection.execute("SELECT s.* FROM samples s JOIN campaigns c ON c.id = s.campaign_id JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE s.client_event_id = ? AND f.organization_id = ?", (event["client_event_id"], organization_id)).fetchone()
        if existing:
            if existing["campaign_id"] != campaign_id or existing["content_hash"] != event["content_hash"]:
                raise ValueError("client_event_conflict")
            return self.sample_with_observation(existing["id"])
        if campaign["status"] in {"review", "paused", "closed"}:
            raise ValueError("campaign_not_collecting")
        metadata = event.get("capture_metadata") or {}
        quality_status, reasons = validate_quality(campaign, metadata)
        sample_id = self._new_id()
        media_path = None
        encoded_media = event.get("media_base64")
        if encoded_media:
            import base64

            try:
                media_bytes = base64.b64decode(encoded_media, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid_media_base64") from exc
            if len(media_bytes) > MAX_MEDIA_BYTES:
                raise ValueError("media_too_large")
            if not is_supported_image(media_bytes):
                raise ValueError("unsupported_media_type")
            if hashlib.sha256(media_bytes).hexdigest() != event["content_hash"].lower():
                raise ValueError("content_hash_mismatch")
            dimensions = image_dimensions(media_bytes)
            if dimensions is None:
                raise ValueError("invalid_image")
            if (metadata.get("width"), metadata.get("height")) != dimensions:
                raise ValueError("image_dimensions_mismatch")
            media_path = str(self.media_dir / f"{sample_id}.bin")
            Path(media_path).write_bytes(media_bytes)
        sample = {
            "id": sample_id,
            "campaign_id": campaign_id,
            "client_event_id": event["client_event_id"],
            "content_hash": event["content_hash"],
            "capture_metadata": json.dumps(metadata, sort_keys=True),
            "quality_status": quality_status,
            "quality_reasons": json.dumps(reasons),
            "media_path": media_path,
            "created_at": utc_now(),
        }
        self.connection.execute(
            "INSERT INTO samples VALUES (:id, :campaign_id, :client_event_id, :content_hash, :capture_metadata, :quality_status, :quality_reasons, :media_path, :created_at)",
            sample,
        )
        self.connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self._new_id(), sample_id, None, 0.0, "no-model-configured", "pending_model", None, None, None, None),
        )
        self._audit(organization_id, actor, "ingested", "sample", sample_id, {"quality_status": quality_status, "content_hash": event["content_hash"]})
        self.connection.commit()
        return self.sample_with_observation(sample_id)

    def sample_with_observation(self, sample_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT s.*, o.id AS observation_id, o.prediction, o.confidence, o.model_version, o.review_status, o.reviewed_prediction, o.review_note, o.reviewed_by, o.reviewed_at FROM samples s JOIN observations o ON o.sample_id = s.id WHERE s.id = ?",
            (sample_id,),
        ).fetchone()
        if not row:
            raise ValueError("sample_not_found")
        result = dict(row)
        result["capture_metadata"] = json.loads(result["capture_metadata"])
        result["quality_reasons"] = json.loads(result["quality_reasons"])
        return result

    def list_observations(self, campaign_id: str, organization_id: str | None = None) -> list[dict[str, Any]]:
        scope = " AND f.organization_id = ?" if organization_id is not None else ""
        parameters = (campaign_id, organization_id) if organization_id is not None else (campaign_id,)
        rows = self.connection.execute(
            "SELECT s.id AS sample_id, s.quality_status, s.quality_reasons, s.capture_metadata, o.* FROM samples s JOIN observations o ON o.sample_id = s.id JOIN campaigns c ON c.id = s.campaign_id JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE s.campaign_id = ?" + scope + " ORDER BY s.created_at",
            parameters,
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["capture_metadata"] = json.loads(item["capture_metadata"])
            item["quality_reasons"] = json.loads(item["quality_reasons"])
            output.append(item)
        return output

    def review_observation(self, observation_id: str, prediction: float, note: str, reviewer: str, organization_id: str = "default") -> dict[str, Any]:
        if not self.connection.execute("SELECT 1 FROM observations o JOIN samples s ON s.id = o.sample_id JOIN campaigns c ON c.id = s.campaign_id JOIN plots p ON p.id = c.plot_id JOIN farms f ON f.id = p.farm_id WHERE o.id = ? AND f.organization_id = ?", (observation_id, organization_id)).fetchone():
            raise ValueError("observation_not_found_or_forbidden")
        latest = self.connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM observation_reviews WHERE observation_id = ?", (observation_id,)).fetchone()
        version = int(latest["version"]) + 1
        reviewed_at = utc_now()
        self.connection.execute(
            "INSERT INTO observation_reviews (id, observation_id, organization_id, version, prediction, note, reviewer, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self._new_id(), observation_id, organization_id, version, prediction, note, reviewer, reviewed_at),
        )
        updated = self.connection.execute(
            "UPDATE observations SET reviewed_prediction = ?, review_note = ?, reviewed_by = ?, reviewed_at = ?, review_status = 'reviewed' WHERE id = ?",
            (prediction, note, reviewer, reviewed_at, observation_id),
        )
        if not updated.rowcount:
            raise ValueError("observation_not_found")
        self._audit(organization_id, reviewer, "reviewed", "observation", observation_id, {"prediction": prediction, "version": version})
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM observations WHERE id = ?", (observation_id,)).fetchone()
        return dict(row)

    def list_observation_reviews(self, observation_id: str, organization_id: str = "default") -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM observation_reviews WHERE observation_id = ? AND organization_id = ? ORDER BY version",
            (observation_id, organization_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def run_inference(self, campaign_id: str, engine: InferenceEngine | None = None, organization_id: str = "default") -> list[dict[str, Any]]:
        campaign = self.get_campaign(campaign_id, organization_id)
        if not campaign:
            raise ValueError("campaign_not_found")
        selected_engine = engine or PendingInferenceEngine()
        model_is_pending = isinstance(selected_engine, PendingInferenceEngine)
        model_is_validated = model_is_pending or self.connection.execute(
            "SELECT 1 FROM model_versions WHERE organization_id = ? AND version = ? AND task = ? AND status = 'validated' LIMIT 1",
            (organization_id, selected_engine.model_version, campaign["task"]),
        ).fetchone() is not None
        rows = self.connection.execute(
            "SELECT s.id, s.media_path, s.capture_metadata, s.quality_status, o.id AS observation_id FROM samples s JOIN observations o ON o.sample_id = s.id WHERE s.campaign_id = ? ORDER BY s.created_at",
            (campaign_id,),
        ).fetchall()
        results = []
        for row in rows:
            metadata = json.loads(row["capture_metadata"])
            if row["quality_status"] != "accepted":
                result = {"observation_id": row["observation_id"], "status": "quality_blocked", "model_version": selected_engine.model_version}
            elif not model_is_validated:
                result = {"observation_id": row["observation_id"], "status": "model_not_validated", "model_version": selected_engine.model_version}
            else:
                prediction = selected_engine.infer(Path(row["media_path"]) if row["media_path"] else None, metadata, campaign["task"])
                self.connection.execute(
                    "UPDATE observations SET prediction = ?, confidence = ?, model_version = ?, review_status = ? WHERE id = ?",
                    (prediction.prediction, prediction.confidence, prediction.model_version, prediction.status, row["observation_id"]),
                )
                result = {"observation_id": row["observation_id"], "prediction": prediction.prediction, "confidence": prediction.confidence, "model_version": prediction.model_version, "status": prediction.status}
            results.append(result)
        self.connection.commit()
        return results

    def evaluate_campaign(self, campaign_id: str, organization_id: str = "default") -> dict[str, Any]:
        if not self.get_campaign(campaign_id, organization_id):
            raise ValueError("campaign_not_found")
        observations = self.list_observations(campaign_id, organization_id)
        references = [
            item for item in observations
            if item["quality_status"] == "accepted" and item["prediction"] is not None and item["reviewed_prediction"] is not None
        ]
        if not references:
            return {
                "status": "insufficient_reference",
                "sample_count": len(observations),
                "evaluated_count": 0,
                "coverage": 0.0,
                "mae": None,
                "median_relative_error": None,
                "error_by_reference_range": {},
            }
        absolute_errors = [abs(item["prediction"] - item["reviewed_prediction"]) for item in references]
        relative_errors = [
            error / abs(item["reviewed_prediction"])
            for item, error in zip(references, absolute_errors)
            if item["reviewed_prediction"] != 0
        ]
        ranges: dict[str, list[tuple[float, float, float | None]]] = {"0-9": [], "10-49": [], "50+": []}
        for item, absolute_error in zip(references, absolute_errors):
            reference = abs(float(item["reviewed_prediction"]))
            bucket = "0-9" if reference < 10 else "10-49" if reference < 50 else "50+"
            relative_error = absolute_error / reference if reference else None
            ranges[bucket].append((absolute_error, reference, relative_error))
        error_by_reference_range = {}
        for bucket, values in ranges.items():
            if not values:
                continue
            range_relative_errors = [value[2] for value in values if value[2] is not None]
            error_by_reference_range[bucket] = {
                "sample_count": len(values),
                "mae": sum(value[0] for value in values) / len(values),
                "median_relative_error": statistics.median(range_relative_errors) if range_relative_errors else None,
                "zero_reference_count": sum(value[1] == 0 for value in values),
            }
        return {
            "status": "evaluated",
            "sample_count": len(observations),
            "evaluated_count": len(references),
            "coverage": len(references) / len(observations) if observations else 0.0,
            "mae": sum(absolute_errors) / len(absolute_errors),
            "median_relative_error": statistics.median(relative_errors) if relative_errors else None,
            "error_by_reference_range": error_by_reference_range,
        }

    def report(self, plot_id: str, organization_id: str = "default") -> dict[str, Any]:
        plot = self.connection.execute("SELECT p.* FROM plots p JOIN farms f ON f.id = p.farm_id WHERE p.id = ? AND f.organization_id = ?", (plot_id, organization_id)).fetchone()
        if not plot:
            raise ValueError("plot_not_found")
        campaigns = self.connection.execute("SELECT * FROM campaigns WHERE plot_id = ? ORDER BY captured_period", (plot_id,)).fetchall()
        campaign_reports = []
        previous_mean: float | None = None
        for campaign in campaigns:
            observations = self.list_observations(campaign["id"], organization_id)
            reviewed = [item["reviewed_prediction"] for item in observations if item["quality_status"] == "accepted" and item["review_status"] == "reviewed"]
            reviewed_mean = sum(reviewed) / len(reviewed) if reviewed else None
            campaign_reports.append({
                "campaign": dict(campaign),
                "sample_count": len(observations),
                "accepted_sample_count": sum(item["quality_status"] == "accepted" for item in observations),
                "reviewed_count": len(reviewed),
                "reviewed_mean": reviewed_mean,
                "delta_from_previous": reviewed_mean - previous_mean if reviewed_mean is not None and previous_mean is not None else None,
                "representativeness": "insufficient_sample" if len(observations) < 5 else "sample_only",
            })
            if reviewed_mean is not None:
                previous_mean = reviewed_mean
        return {"plot": dict(plot), "campaigns": campaign_reports, "extrapolation_allowed": False}

    def coverage(self, plot_id: str, organization_id: str = "default") -> dict[str, Any]:
        plot = self.connection.execute(
            "SELECT p.* FROM plots p JOIN farms f ON f.id = p.farm_id WHERE p.id = ? AND f.organization_id = ?",
            (plot_id, organization_id),
        ).fetchone()
        if not plot:
            raise ValueError("plot_not_found")
        rows = self.connection.execute(
            "SELECT s.id AS sample_id, s.quality_status, s.capture_metadata, c.id AS campaign_id, c.captured_period FROM samples s JOIN campaigns c ON c.id = s.campaign_id WHERE c.plot_id = ? ORDER BY s.created_at",
            (plot_id,),
        ).fetchall()
        points = []
        counts = {"sample_count": len(rows), "located_count": 0, "accepted_count": 0, "pending_location_count": 0, "out_of_domain_count": 0}
        for row in rows:
            metadata = json.loads(row["capture_metadata"])
            latitude = metadata.get("latitude")
            longitude = metadata.get("longitude")
            if latitude is not None and longitude is not None:
                counts["located_count"] += 1
                points.append({"sample_id": row["sample_id"], "campaign_id": row["campaign_id"], "captured_period": row["captured_period"], "latitude": latitude, "longitude": longitude, "quality_status": row["quality_status"]})
            if row["quality_status"] == "accepted":
                counts["accepted_count"] += 1
            elif row["quality_status"] == "pending_location":
                counts["pending_location_count"] += 1
            elif row["quality_status"] == "out_of_domain":
                counts["out_of_domain_count"] += 1
        return {"plot": dict(plot), **counts, "points": points, "extrapolation_allowed": False}


def validate_quality(campaign: sqlite3.Row, metadata: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    width = metadata.get("width", 0)
    height = metadata.get("height", 0)
    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    numeric_values = (width, height, metadata.get("blur_score", 0), latitude, longitude)
    if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))) for value in numeric_values):
        return "rejected", ["metadata_invalid"]
    if width < 640 or height < 480:
        reasons.append("resolution_below_minimum")
    if metadata.get("blur_score", 0) < 0.4:
        reasons.append("blur_score_below_minimum")
    if metadata.get("crop") and metadata["crop"] != campaign["crop"]:
        reasons.append("crop_out_of_domain")
    if latitude is None or longitude is None:
        reasons.append("location_missing")
    elif all(campaign[key] is not None for key in ("min_lat", "min_lon", "max_lat", "max_lon")) and not (
        campaign["min_lat"] <= latitude <= campaign["max_lat"] and campaign["min_lon"] <= longitude <= campaign["max_lon"]
    ):
        reasons.append("location_out_of_plot")
    if "crop_out_of_domain" in reasons:
        return "out_of_domain", reasons
    if "location_missing" in reasons or "location_out_of_plot" in reasons:
        return "pending_location", reasons
    if reasons:
        return "rejected", reasons
    return "accepted", reasons
