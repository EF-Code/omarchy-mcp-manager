import os
import json
import tempfile
import unittest
from pathlib import Path

from mcp_manager.conversion import conversion_preview, find_server
from mcp_manager.discovery import public_scan, scan
from mcp_manager.paths import manager_dirs
from mcp_manager.planner import PlanError, apply, plan, plan_restore


class PlannerTests(unittest.TestCase):
    def test_plan_rejects_regular_parent_directory_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("codex\n", encoding="utf-8")
            source_dir = home / ".codex"
            source_dir.mkdir()
            config = source_dir / "config.toml"
            original = '[mcp_servers."alpha"]\ncommand = "echo"\n'
            config.write_text(original, encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            cwd = Path.cwd()
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                os.chdir(home)
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["adapterId"] == "codex" and source["exists"])
                preview = plan({"sourceId": source["sourceId"], "action": "set-enabled", "serverName": "alpha", "payload": {"enabled": False}})
                moved = home / ".codex-planned"
                source_dir.rename(moved)
                source_dir.mkdir()
                os.link(moved / "config.toml", config)
                with self.assertRaises(PlanError):
                    apply(preview["planId"], {})
                self.assertEqual((moved / "config.toml").read_text(encoding="utf-8"), original)
                self.assertEqual(config.read_text(encoding="utf-8"), original)
            finally:
                os.chdir(cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_codex_plan_apply_and_stale_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("codex\n", encoding="utf-8")
            (home / ".codex").mkdir(parents=True)
            config = home / ".codex/config.toml"
            config.write_text('[mcp_servers."alpha"]\ncommand = "echo"\n\n[settings]\nkeep = true\n', encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            cwd = Path.cwd()
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "run")})
                os.chdir(home)
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["adapterId"] == "codex" and source["exists"])
                preview = plan({"sourceId": source["sourceId"], "action": "set-enabled", "serverName": "alpha", "payload": {"enabled": False}})
                self.assertTrue(preview["preview"]["confirmRequired"])
                config.write_text(config.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
                with self.assertRaises(Exception):
                    apply(preview["planId"], {})
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["adapterId"] == "codex" and source["exists"])
                preview = plan({"sourceId": source["sourceId"], "action": "set-enabled", "serverName": "alpha", "payload": {"enabled": False}})
                apply(preview["planId"], {})
                changed = config.read_text(encoding="utf-8")
                self.assertIn("enabled = false", changed)
                self.assertIn("[settings]", changed)
                self.assertIn("keep = true", changed)
            finally:
                os.chdir(cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_restore_requires_and_uses_a_fingerprint_bound_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("codex\n", encoding="utf-8")
            (home / ".codex").mkdir(parents=True)
            config = home / ".codex/config.toml"
            original = '[mcp_servers."alpha"]\ncommand = "echo"\n'
            config.write_text(original, encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            cwd = Path.cwd()
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                os.chdir(home)
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["adapterId"] == "codex" and source["exists"])
                change = plan({"sourceId": source["sourceId"], "action": "set-enabled", "serverName": "alpha", "payload": {"enabled": False}})
                committed = apply(change["planId"], {})
                restore = plan_restore(committed["backupId"], source["sourceId"])
                self.assertTrue(restore["preview"]["confirmRequired"])
                self.assertEqual(restore["action"], "restore")
                apply(restore["planId"], {})
                self.assertEqual(config.read_text(encoding="utf-8"), original)
            finally:
                os.chdir(cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_secret_replacements_never_enter_persisted_plans_or_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("gemini\n", encoding="utf-8")
            (home / ".gemini").mkdir(parents=True)
            config = home / ".gemini/settings.json"
            config.write_text('{"mcpServers":{"existing":{"command":"echo","env":{"KEEP":"unchanged"}}}}\n', encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            cwd = Path.cwd()
            secret = "fixture-private-value-92731"
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                os.chdir(home)
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["adapterId"] == "gemini" and source["exists"])
                with self.assertRaises(PlanError):
                    plan({"sourceId": source["sourceId"], "action": "upsert-server", "serverName": "existing", "payload": {"name": "existing", "env": {"API_TOKEN": secret}}})
                request = {"sourceId": source["sourceId"], "action": "upsert-server", "serverName": "existing", "payload": {"name": "existing"}, "secretReplacements": {"env.API_TOKEN": secret}}
                preview = plan(request)
                state = manager_dirs(create=True)["state"]
                self.assertNotIn(secret, (state / "plans" / f"{preview['planId']}.json").read_text(encoding="utf-8"))
                apply(preview["planId"], {"secretReplacements": {"env.API_TOKEN": secret}})
                self.assertIn(secret, config.read_text(encoding="utf-8"))
                self.assertIn('"KEEP":"unchanged"', config.read_text(encoding="utf-8"))
                self.assertNotIn(secret, (state / "history.json").read_text(encoding="utf-8"))
                self.assertNotIn(secret, (state / "plans" / f"{preview['planId']}.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_plan_ids_reject_path_traversal(self):
        with self.assertRaises(PlanError):
            apply("../history", {})

    def test_cross_agent_copy_preview_plans_and_applies_to_selected_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("codex\n", encoding="utf-8")
            (home / ".codex").mkdir(parents=True)
            codex_config = home / ".codex/config.toml"
            codex_original = '[mcp_servers."dune"]\nurl = "https://api.dune.test/mcp/v1"\n'
            codex_config.write_text(codex_original, encoding="utf-8")
            antigravity_dir = home / ".gemini/config"
            antigravity_dir.mkdir(parents=True)
            antigravity_config = antigravity_dir / "mcp_config.json"
            antigravity_config.write_text('{"keep":true,"mcpServers":{}}\n', encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            cwd = Path.cwd()
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "runtime")})
                os.chdir(home)
                scanned = public_scan(scan())
                source = next(source for agent in scanned["agents"] if agent["id"] == "codex" for source in agent["sources"] if source["exists"])
                server = find_server(scanned, source["sourceId"], "dune")
                conversion = conversion_preview(server, "antigravity", scanned)
                self.assertTrue(conversion["canApply"])
                self.assertEqual(conversion["targetSourceDisplay"], "~/.gemini/config/mcp_config.json")
                destination_secret = "fixture-destination-credential"
                antigravity_config.write_text(
                    '{"keep":true,"mcpServers":{"dune":{"command":"old-tool","headers":{"Authorization":"'
                    + destination_secret
                    + '"}}}}\n',
                    encoding="utf-8",
                )
                request = {
                    "sourceId": conversion["targetSourceId"],
                    "action": "copy-server",
                    "serverName": conversion["payload"]["name"],
                    "payload": conversion["payload"],
                }
                planned = plan(request)
                self.assertTrue(planned["preview"]["confirmRequired"])
                self.assertTrue(any("update the existing" in warning for warning in planned["preview"]["warnings"]))
                self.assertTrue(any("credential fields remain" in warning for warning in planned["preview"]["warnings"]))
                self.assertNotIn(destination_secret, repr(planned))
                apply(planned["planId"], {})
                changed = json.loads(antigravity_config.read_text(encoding="utf-8"))
                self.assertTrue(changed["keep"])
                self.assertEqual(changed["mcpServers"]["dune"]["url"], "https://api.dune.test/mcp/v1")
                self.assertEqual(changed["mcpServers"]["dune"]["headers"]["Authorization"], destination_secret)
                self.assertEqual(codex_config.read_text(encoding="utf-8"), codex_original)
            finally:
                os.chdir(cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
