import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sre_platform.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "demo.db"

    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["sre-platform", "--db", str(self.db), *args]):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_demo_persists_and_reopens(self):
        code, text, error = self.invoke("demo")
        self.assertEqual((code, error), (0, ""))
        result = json.loads(text)
        self.assertEqual(result["before_effective_increase"]["status"], "awaiting_recovery")
        self.assertEqual(result["simulated_recovery"]["status"], "recovered")
        incident_id = result["investigation"]["incident_id"]
        code, text, error = self.invoke("show", incident_id)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(text)["status"], "recovered")
        code, text, error = self.invoke("audit", incident_id)
        self.assertEqual(len(json.loads(text)), 4)

    def test_module_entrypoint(self):
        result = subprocess.run(
            [sys.executable, "-m", "sre_platform", "--db", str(self.db), "demo"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "synthetic_offline")

    def test_bad_inputs_never_create_database(self):
        for content in ('{"x":1,"x":2}', "{", "x" * 65537, "\udcff"):
            with self.subTest(content=content[:10]):
                source = Path(self.temp.name) / "invalid.json"
                source.write_bytes(content.encode("utf-8", errors="surrogateescape"))
                code, text, error = self.invoke("investigate", str(source))
                self.assertEqual((code, text), (2, ""))
                self.assertIn("error", json.loads(error))
                self.assertFalse(self.db.exists())

    def test_investigate_propose_and_pending_exit_code(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "quota-exhausted.json"
        value = json.loads(fixture.read_text())
        value["observed_at"] = datetime.now(timezone.utc).isoformat()
        source = Path(self.temp.name) / "evidence.json"
        source.write_text(json.dumps(value))
        code, text, _ = self.invoke("investigate", str(source))
        self.assertEqual(code, 0)
        incident_id = json.loads(text)["incident_id"]
        code, text, error = self.invoke("propose", incident_id, "--target-vcpus", "64")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("value        = 64", json.loads(text)["terraform_proposal"])
        code, text, error = self.invoke("verify", incident_id, str(source))
        self.assertEqual((code, error), (3, ""))
        self.assertEqual(json.loads(text)["status"], "awaiting_recovery")

    def test_invalid_explanation_does_not_persist_incident(self):
        fixture = Path(__file__).resolve().parents[1] / "examples" / "quota-exhausted.json"
        value = json.loads(fixture.read_text())
        value["observed_at"] = datetime.now(timezone.utc).isoformat()
        source = Path(self.temp.name) / "evidence.json"
        source.write_text(json.dumps(value))
        explanation = Path(self.temp.name) / "explanation.json"
        explanation.write_text(json.dumps({
            "cause": "delete_cluster", "evidence_ids": [], "summary": "Unsafe proposal",
        }))
        code, text, error = self.invoke(
            "investigate", str(source), "--explanation", str(explanation),
        )
        self.assertEqual((code, text), (2, ""))
        self.assertIn("cannot override", json.loads(error)["error"])
        self.assertFalse(self.db.exists())
        explanation.write_text("null")
        code, text, error = self.invoke(
            "investigate", str(source), "--explanation", str(explanation),
        )
        self.assertEqual((code, text), (2, ""))
        self.assertIn("requires exactly", json.loads(error)["error"])
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
