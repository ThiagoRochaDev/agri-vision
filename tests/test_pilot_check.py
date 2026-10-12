import unittest
import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pilot_check import main, validate


class PilotCheckTests(unittest.TestCase):
    def test_valid_pilot_config_passes(self) -> None:
        config = {
            "crop": "café",
            "task": "contagem de frutos",
            "partner": "fazenda piloto",
            "protocol_version": "v1",
            "annotation_owner": "agrônomo responsável",
            "baseline": "MAE contra contagem humana",
            "consent_scope": "uso interno do piloto",
            "review_protocol": "dupla revisão das referências",
            "data_source": "campanha autorizada",
            "evaluation_groups": ["fazenda-reserva"],
            "extrapolation_allowed": False,
        }
        self.assertEqual(validate(config), [])

    def test_incomplete_pilot_config_is_rejected(self) -> None:
        failures = validate({"crop": "café", "extrapolation_allowed": True, "evaluation_groups": []})
        self.assertIn("task_missing", failures)
        self.assertIn("data_source_missing", failures)
        self.assertIn("evaluation_groups_missing_or_invalid", failures)
        self.assertIn("extrapolation_must_remain_false", failures)

    def test_cli_accepts_completed_config(self) -> None:
        config = {
            "crop": "café",
            "task": "contagem de frutos",
            "partner": "fazenda piloto",
            "protocol_version": "v1",
            "annotation_owner": "agrônomo responsável",
            "baseline": "MAE contra contagem humana",
            "consent_scope": "uso interno do piloto",
            "review_protocol": "dupla revisão das referências",
            "data_source": "campanha autorizada",
            "evaluation_groups": ["fazenda-reserva"],
            "extrapolation_allowed": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pilot.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            output = StringIO()
            with patch("sys.argv", ["pilot_check.py", str(path)]), redirect_stdout(output):
                result = main()
        self.assertEqual(result, 0)
        self.assertIn("OK pilot gate", output.getvalue())
