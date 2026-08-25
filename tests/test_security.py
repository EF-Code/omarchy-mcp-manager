import contextlib
import io
import json
import os
import stat
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp_manager.cli import main as cli_main
from mcp_manager.paths import UnsafePathError, manager_dirs, metadata, read_bytes, validate_path
from mcp_manager.redaction import sanitize_text
from mcp_manager.transaction import OwnerLock, TransactionError, atomic_file, commit, history, recover


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
            traversal = root / "child" / ".." / "real.json"
            with self.assertRaises(UnsafePathError):
                validate_path(traversal)
            real.chmod(0o660)
            with self.assertRaises(UnsafePathError):
                validate_path(real)

    def test_broad_permissions_are_inspectable_but_not_mutable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            broad = root / "broad"
            broad.mkdir(mode=0o777)
            broad.chmod(0o777)
            source = broad / "config.json"
            source.write_text('{"mcpServers":{"visible":{"command":"tool"}}}\n', encoding="utf-8")
            source.chmod(0o666)

            data, info = read_bytes(source, require_private_permissions=False)

            self.assertIn(b'"visible"', data)
            self.assertEqual(info.st_uid, os.getuid())
            with self.assertRaises(UnsafePathError):
                read_bytes(source)

    def test_drift_refuses_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            path.write_text("old\n", encoding="utf-8")
            saved = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                old, info = read_bytes(path)
                base = metadata(info, old)
                path.write_text("external\n", encoding="utf-8")
                with self.assertRaises(TransactionError):
                    commit("src-drift", path, b"new\n", base, operation_id="op-drift", history_entry={"action": "test"})
                self.assertEqual(path.read_text(encoding="utf-8"), "external\n")
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_intermediate_directory_swap_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "source"
            parent.mkdir()
            path = parent / "config.json"
            path.write_text("old\n", encoding="utf-8")
            attacker = root / "attacker"
            attacker.mkdir()
            attacker_path = attacker / "config.json"
            attacker_path.write_text("attacker\n", encoding="utf-8")
            moved = root / "source-moved"
            old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                original, info = read_bytes(path)
                real_validate = validate_path
                calls = 0

                def swap_after_validation(candidate, **kwargs):
                    nonlocal calls
                    result = real_validate(candidate, **kwargs)
                    calls += 1
                    if calls == 2:
                        parent.rename(moved)
                        parent.symlink_to(attacker, target_is_directory=True)
                    return result

                with mock.patch("mcp_manager.transaction.validate_path", side_effect=swap_after_validation):
                    with self.assertRaises(UnsafePathError):
                        commit("src-swap", path, b"new\n", metadata(info, original), operation_id="op-swap", history_entry={"action": "test"})
                self.assertEqual((moved / "config.json").read_text(encoding="utf-8"), "old\n")
                self.assertEqual(attacker_path.read_text(encoding="utf-8"), "attacker\n")
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

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
        text = "Authorization=real-secret-value token=fixture-token-value"
        safe = sanitize_text(text, ["real-secret-value", "fixture-token-value"])
        self.assertNotIn("real-secret-value", safe)
        self.assertNotIn("fixture-token-value", safe)

    def test_owner_lock_serializes_writers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ["XDG_STATE_HOME"] = str(root / "state")
                os.environ["XDG_CACHE_HOME"] = str(root / "cache")
                os.environ["XDG_RUNTIME_DIR"] = str(root / "runtime")
                with OwnerLock("same-source"):
                    with self.assertRaises(TransactionError):
                        with OwnerLock("same-source"):
                            pass
                with OwnerLock("same-source"):
                    pass
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_commit_never_changes_parent_directory_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "project"
            parent.mkdir(mode=0o755)
            path = parent / "config.json"
            path.write_text("old\n", encoding="utf-8")
            old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                old, info = read_bytes(path)
                commit("src-mode", path, b"new\n", metadata(info, old), operation_id="op-mode", history_entry={"action": "test"})
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o755)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_semantic_verification_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            path.write_text("old\n", encoding="utf-8")
            old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                old, info = read_bytes(path)
                with self.assertRaises(TransactionError):
                    commit("src-verify", path, b"new\n", metadata(info, old), operation_id="op-verify", history_entry={"action": "test"}, verify=lambda _data: (_ for _ in ()).throw(ValueError("bad semantics")))
                self.assertEqual(path.read_bytes(), old)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_all_transaction_failpoints_leave_a_complete_file(self):
        early = {"before-temp", "after-write", "after-fsync", "after-replace", "after-dir-fsync", "after-readback"}
        for failpoint in sorted(early | {"after-history", "after-cleanup"}):
            with self.subTest(failpoint=failpoint), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / "config.json"
                old = b'{"state":"old"}\n'
                new = b'{"state":"new"}\n'
                path.write_bytes(old)
                old_env = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "MCP_MANAGER_FAILPOINT")}
                try:
                    os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime"), "MCP_MANAGER_FAILPOINT": failpoint})
                    before, info = read_bytes(path)
                    with self.assertRaises(TransactionError):
                        commit("src-" + failpoint, path, new, metadata(info, before), operation_id="op-" + failpoint, history_entry={"action": "test"})
                    self.assertEqual(path.read_bytes(), old if failpoint in early else new)
                    os.environ.pop("MCP_MANAGER_FAILPOINT", None)
                    recovery = recover()
                    self.assertEqual(recovery["ambiguous"], 0)
                finally:
                    for key, value in old_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

    def test_state_directory_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            real = root / "real-state"
            real.mkdir()
            link = root / "state-link"
            link.symlink_to(real, target_is_directory=True)
            old = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(link), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                with self.assertRaises(UnsafePathError):
                    manager_dirs(create=True)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_backups_history_and_locks_are_owner_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            path.write_text("old\n", encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                data, info = read_bytes(path)
                commit("src-perms", path, b"new\n", metadata(info, data), operation_id="op-perms", history_entry={"action": "test"})
                dirs = manager_dirs(create=True)
                sensitive = list((dirs["state"] / "backups").glob("*")) + [dirs["state"] / "history.json"] + list((dirs["runtime"] / "locks").glob("*"))
                self.assertTrue(history())
                for item in sensitive:
                    with self.subTest(path=item.name):
                        self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o600)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_backup_retention_keeps_the_newest_and_marks_expired_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            path.write_text("state-0\n", encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                for index in range(1, 8):
                    data, info = read_bytes(path)
                    commit("src-retention", path, f"state-{index}\n".encode(), metadata(info, data), operation_id=f"op-retention-{index}", history_entry={"action": "test", "sourceId": "src-retention"})
                entries = history(20)
                self.assertEqual(sum(1 for item in entries if item["backupAvailable"]), 5)
                self.assertFalse(entries[0]["backupAvailable"])
                self.assertTrue(entries[-1]["backupAvailable"])
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_crash_recovery_finalizes_replaced_source_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "config.json"
            current = b'{"state":"new"}\n'
            path.write_bytes(current)
            old = {key: os.environ.get(key) for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                dirs = manager_dirs(create=True)
                temp_name = ".config.json.mcp-manager-crashfixture"
                (root / temp_name).write_bytes(b"temporary")
                journal = {
                    "schemaVersion": 1,
                    "operationId": "op-crash",
                    "sourceId": "src-crash",
                    "path": str(path),
                    "base": {"fingerprint": "sha256:" + hashlib.sha256(b'{"state":"old"}\n').hexdigest()},
                    "newFingerprint": "sha256:" + hashlib.sha256(current).hexdigest(),
                    "backupId": "backup_crashfixture",
                    "tempName": temp_name,
                    "historyEntry": {"action": "test", "sourceId": "src-crash"},
                    "status": "replaced",
                }
                atomic_file(dirs["state"] / "journal" / "op-crash.json", (json.dumps(journal) + "\n").encode())
                result = recover()
                self.assertEqual(result, {"finalized": 1, "ambiguous": 0})
                self.assertFalse((root / temp_name).exists())
                self.assertTrue(any(item.get("operationId") == "op-crash" for item in history()))
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_cli_stdin_errors_are_one_secret_safe_json_object(self):
        secret = "fixture-stdin-secret-48391"
        output = io.StringIO()
        request = json.dumps({"sourceId": "src_deadbeef", "action": "upsert-server", "serverName": "x", "payload": {"command": "tool", "args": ["--api-key=" + secret]}})
        with contextlib.redirect_stdout(output), mock.patch("sys.stdin", io.StringIO(request + "\n")):
            code = cli_main(["plan-stdin"])
        rendered = output.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(len(rendered.splitlines()), 1)
        self.assertNotIn(secret, rendered)
        self.assertFalse(json.loads(rendered)["ok"])

        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch("sys.stdin", io.StringIO("")):
            code = cli_main(["plan-stdin"])
        self.assertEqual(code, 1)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid-request")

        output = io.StringIO()
        duplicate = '{"sourceId":"one","sourceId":"two","action":"remove-server","serverName":"x"}'
        with contextlib.redirect_stdout(output), mock.patch("sys.stdin", io.StringIO(duplicate + "\n")):
            code = cli_main(["plan-stdin"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid-request")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli_main(["plan-json", "--json", request])
        self.assertEqual(code, 1)
        self.assertNotIn(secret, output.getvalue())

    def test_qml_never_places_request_json_in_process_arguments(self):
        controller = (Path(__file__).parent.parent / "Controller.qml").read_text(encoding="utf-8")
        self.assertNotIn('"plan-json"', controller)
        self.assertNotIn('"apply-json"', controller)
        self.assertIn('run(["plan-stdin"], "plan", JSON.stringify(request))', controller)
        self.assertIn("stdinEnabled: true", controller)


if __name__ == "__main__":
    unittest.main()
