import os
import tempfile
import unittest
from pathlib import Path

from mcp_manager.adapters import adapter_by_id, normalized_servers, parse_source, patch_source
from mcp_manager.discovery import scan
from mcp_manager.conversion import comparison, conversion_preview
from mcp_manager.json_source import DuplicateKeyError, SourceParseError, loads
from mcp_manager.toml_source import parse as parse_toml


class AdapterTests(unittest.TestCase):
    def test_catalog_contains_every_required_agent(self):
        expected = {"codex", "claude", "opencode", "gemini", "antigravity", "copilot", "crush", "pi", "omp", "grok"}
        self.assertTrue(expected.issubset({adapter.id for adapter in __import__("mcp_manager.adapters", fromlist=["adapters"]).adapters()}))

    def test_jsonc_targeted_toggle_preserves_unrelated_bytes(self):
        source = "{\r\n  // keep this comment\r\n  \"name\": \"demo\",\r\n  \"mcpServers\": {\r\n    \"alpha\": {\r\n      \"command\": \"echo\",\r\n      \"disabled\": false,\r\n      \"x-unknown\": {\"keep\": true}\r\n    },\r\n  },\r\n}\r\n"
        adapter = adapter_by_id("gemini")
        changed = patch_source(adapter, source, Path("settings.jsonc"), action="set-enabled", name="alpha", payload={"enabled": False})
        self.assertIn("x-unknown", changed)
        self.assertIn("// keep this comment", changed)
        self.assertIn('"disabled": true', changed)
        self.assertIn('"name": "demo"', changed)
        self.assertEqual(changed, (Path(__file__).parent / "golden/jsonc-toggle.golden").read_bytes().decode("utf-8"))
        parsed = parse_source(adapter, changed, Path("settings.jsonc"))
        self.assertTrue(parsed["servers"]["alpha"]["disabled"])

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(DuplicateKeyError):
            loads('{"mcpServers": {}, "mcpServers": {}}')
        with self.assertRaises(DuplicateKeyError):
            loads('{"mcpServers": {}, "mcpServers": {}}', jsonc=True)

    def test_strict_json_rejects_jsonc(self):
        with self.assertRaises(SourceParseError):
            loads('{"a": 1,}', jsonc=False)

    def test_codex_table_family_edit(self):
        source = "title = \"keep\"\r\n\r\n[mcp_servers.\"alpha.name\"]\r\ncommand = \"echo\"\r\nargs = [\"one\"]\r\n\r\n[mcp_servers.\"alpha.name\".env]\nTOKEN = \"$TOKEN\"\r\n\r\n[other]\nvalue = 1\r\n"
        adapter = adapter_by_id("codex")
        changed = patch_source(adapter, source, Path("config.toml"), action="set-enabled", name="alpha.name", payload={"enabled": False})
        self.assertIn('title = "keep"', changed)
        self.assertIn("[other]", changed)
        self.assertIn("enabled = false", changed)
        parse_toml(changed)
        self.assertEqual(changed, (Path(__file__).parent / "golden/toml-toggle.golden").read_bytes().decode("utf-8"))

    def test_secret_safe_normalization(self):
        adapter = adapter_by_id("gemini")
        parsed = parse_source(adapter, '{"mcpServers":{"x":{"command":"echo","env":{"API_KEY":"real-secret-value","MODE":"dev"},"url":"https://example.test/mcp?token=real-secret-value"}}}', Path("settings.json"))
        server = normalized_servers(adapter, parsed, "src_test")[0]
        rendered = repr(server)
        self.assertNotIn("real-secret-value", rendered)
        self.assertIn("API_KEY", rendered)
        self.assertIn("set", rendered)

    def test_conversion_preview_is_explicitly_lossy_and_secret_safe(self):
        server = {"name": "remote", "transport": "sse", "url": {"display": "https://example.test/mcp?token=<redacted>", "state": "set"}, "headers": [{"name": "Authorization", "state": "set"}], "environment": []}
        preview = conversion_preview(server, "codex")
        self.assertTrue(preview["lossy"])
        self.assertTrue(any("secret" in warning.lower() or "header" in warning.lower() for warning in preview["warnings"]))
        self.assertNotIn("real", repr(preview))

    def test_comparison_matrix_has_agent_columns(self):
        result = comparison({"agents": [{"id": "codex", "name": "Codex", "sources": [{"sourceId": "s", "servers": [{"name": "alpha", "enabled": True, "transport": "stdio"}]}]}]})
        self.assertEqual(result["serverNames"], ["alpha"])
        self.assertEqual(result["agents"][0]["servers"]["alpha"]["state"], "enabled")

    def test_discovery_precedence_and_antigravity_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = root / "home"
            bin_dir = root / "bin"
            (home / ".config/omarchy/defaults").mkdir(parents=True)
            (home / ".config/omarchy/defaults/agent").write_text("gemini\n", encoding="utf-8")
            (home / ".gemini").mkdir(parents=True)
            (home / ".gemini/settings.json").write_text('{"mcpServers":{"global":{"command":"echo"}}}\n', encoding="utf-8")
            (home / ".gemini/config").mkdir(parents=True)
            (home / ".gemini/config/mcp_config.json").write_text('{"mcpServers":{"ag":{"command":"echo"}}}\n', encoding="utf-8")
            bin_dir.mkdir()
            for executable in ("gemini", "agy"):
                item = bin_dir / executable
                item.write_text("#!/bin/sh\n", encoding="utf-8")
                item.chmod(0o755)
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR", "PATH")}
            old_cwd = Path.cwd()
            try:
                os.environ.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "run"), "PATH": str(bin_dir)})
                os.chdir(home)
                result = scan()
            finally:
                os.chdir(old_cwd)
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            agents = result["agents"]
            self.assertEqual(agents[0]["id"], "gemini")
            self.assertTrue(agents[0]["isOmarchyDefault"])
            anti = next(agent for agent in agents if agent["id"] == "antigravity")
            self.assertIn("executable", anti["detectedBy"])
            self.assertIn("config", anti["detectedBy"])
            self.assertNotEqual(anti["id"], agents[0]["id"])


if __name__ == "__main__":
    unittest.main()
