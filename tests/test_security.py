import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from mcp_manager.paths import UnsafePathError, metadata, read_bytes, validate_path
from mcp_manager.redaction import sanitize_text
from mcp_manager.transaction import TransactionError, commit, recover


class SecurityTests(unittest.TestCase):
    def test_symlink_and_unsafe_parent_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            real = root / "real.json"
            real.write_text("{}\n", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(real)
            with self.assertRaises(UnsafePathError):
                validate_path(link)
            broad = root / "broad"
            broad.mkdir()
            broad.chmod(0o777)
            candidate = broad / "config.json"
            candidate.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(UnsafePathError):
                validate_path(candidate)

    def test_drift_refuses_write(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text("old\n", encoding="utf-8")
            old, info = read_bytes(path)
            base = metadata(info, old)
            path.write_text("external\n", encoding="utf-8")
            with self.assertRaises(TransactionError):
                commit("src-drift", path, b"new\n", base, operation_id="op-drift", history_entry={"action": "test"})
            self.assertEqual(path.read_text(encoding="utf-8"), "external\n")

    def test_failpoint_rolls_back_to_valid_preimage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state"
            cache = root / "cache"
            runtime = root / "runtime"
            old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ["XDG_STATE_HOME"] = str(state)
                os.environ["XDG_CACHE_HOME"] = str(cache)
                os.environ["XDG_RUNTIME_DIR"] = str(runtime)
                path = root / "config.json"
                path.write_text('{"ok":true}\n', encoding="utf-8")
                old, info = read_bytes(path)
                base = metadata(info, old)
                os.environ["MCP_MANAGER_FAILPOINT"] = "after-replace"
                with self.assertRaises(TransactionError):
                    commit("src-fail", path, b'{"ok":false}\n', base, operation_id="op-fail", history_entry={"action": "test"})
                self.assertEqual(path.read_bytes(), old)
                os.environ.pop("MCP_MANAGER_FAILPOINT", None)
                self.assertIsInstance(recover(), dict)
            finally:
                os.environ.pop("MCP_MANAGER_FAILPOINT", None)
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_secret_sanitizer(self):
        text = "Authorization: Bearer real-secret-value sk-1234567890abcd"
        safe = sanitize_text(text, ["real-secret-value"])
        self.assertNotIn("real-secret-value", safe)
        self.assertNotIn("sk-1234567890abcd", safe)


if __name__ == "__main__":
    unittest.main()
