import os
import tempfile
import unittest
from pathlib import Path

from mcp_manager.discovery import scan
from mcp_manager.planner import apply, plan


class PlannerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
