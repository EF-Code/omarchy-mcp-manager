import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from mcp_manager.diagnostic_state import annotate_diagnostics, ignore_all, ignore_diagnostic, restore_all
from mcp_manager.paths import UnsafePathError, manager_dirs


class DiagnosticStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = {key: os.environ.get(key) for key in ("HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
        os.environ.update({
            "HOME": str(root / "home"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "XDG_RUNTIME_DIR": str(root / "run"),
        })

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    @staticmethod
    def fixture():
        server_diagnostic = {"code": "relative-cwd", "severity": "warning", "label": "Relative working directory"}
        source_diagnostic = {"code": "cross-agent-drift", "severity": "info", "label": "Definition differs"}
        agents = [{
            "id": "codex",
            "sources": [{
                "sourceId": "src_opaque",
                "pathDisplay": "~/.codex/config.toml",
                "servers": [{"name": "alpha", "diagnostics": [server_diagnostic]}],
                "diagnostics": [server_diagnostic, source_diagnostic],
            }],
        }]
        return agents, []

    def test_ignores_are_opaque_owner_only_and_reversible(self):
        agents, general = self.fixture()
        self.assertEqual(annotate_diagnostics(agents, general), (2, 0))
        diagnostic_id = agents[0]["sources"][0]["servers"][0]["diagnostics"][0]["diagnosticId"]
        valid_ids = {item["diagnosticId"] for item in agents[0]["sources"][0]["diagnostics"]}
        self.assertEqual(ignore_diagnostic(diagnostic_id, valid_ids), 1)
        self.assertEqual(annotate_diagnostics(agents, general), (1, 1))
        state_path = manager_dirs(create=True)["state"] / "ignored-diagnostics.json"
        self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
        raw = state_path.read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw), [diagnostic_id])
        self.assertNotIn("config.toml", raw)
        self.assertNotIn("Relative working directory", raw)
        self.assertEqual(ignore_all(valid_ids), 2)
        self.assertEqual(annotate_diagnostics(agents, general), (0, 2))
        self.assertEqual(restore_all(), 0)
        self.assertEqual(annotate_diagnostics(agents, general), (2, 0))

    def test_unknown_id_and_symlink_state_are_rejected(self):
        agents, general = self.fixture()
        annotate_diagnostics(agents, general)
        valid_ids = {item["diagnosticId"] for item in agents[0]["sources"][0]["diagnostics"]}
        with self.assertRaises(ValueError):
            ignore_diagnostic("diag_" + "0" * 24, valid_ids)
        state_path = manager_dirs(create=True)["state"] / "ignored-diagnostics.json"
        target = Path(self.temp.name) / "target.json"
        target.write_text("[]\n", encoding="utf-8")
        state_path.symlink_to(target)
        with self.assertRaises(UnsafePathError):
            ignore_all(valid_ids)


if __name__ == "__main__":
    unittest.main()
