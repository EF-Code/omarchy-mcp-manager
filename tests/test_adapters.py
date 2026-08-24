import os
import tempfile
import unittest
from pathlib import Path

from mcp_manager.adapters import adapter_by_id, normalized_servers, parse_source, patch_source
from mcp_manager.discovery import scan
from mcp_manager.conversion import comparison, conversion_batch_preview, conversion_preview
from mcp_manager.cli import _forget, _register
from mcp_manager.json_source import DuplicateKeyError, SourceParseError, loads
from mcp_manager.redaction import normalized_server, redact_command, redact_url, response_safe
from mcp_manager.toml_source import TomlSourceError, parse as parse_toml


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

    def test_strict_json_rejects_nonstandard_constants_and_deep_input(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant), self.assertRaises(SourceParseError):
                loads('{"value":' + constant + '}')
        deeply_nested = "[" * 66 + "0" + "]" * 66
        with self.assertRaises(SourceParseError):
            loads(deeply_nested)

    def test_jsonc_add_remove_and_rename_preserve_valid_trailing_commas(self):
        adapter = adapter_by_id("gemini")
        source = '{\r\n  "keep": true,\r\n  "mcpServers": {\r\n    "alpha": {\r\n      // selected comment\r\n      "command": "echo",\r\n    },\r\n  },\r\n}\r\n'
        added = patch_source(adapter, source, Path("settings.jsonc"), action="duplicate-server", name="alpha", payload={"name": "beta", "command": "printf", "args": []})
        parsed = parse_source(adapter, added, Path("settings.jsonc"))
        self.assertEqual(set(parsed["servers"]), {"alpha", "beta"})
        self.assertIn("// selected comment", added)
        removed = patch_source(adapter, added, Path("settings.jsonc"), action="remove-server", name="beta", payload={})
        self.assertEqual(set(parse_source(adapter, removed, Path("settings.jsonc"))["servers"]), {"alpha"})
        renamed = patch_source(adapter, removed, Path("settings.jsonc"), action="upsert-server", name="alpha", payload={"name": "renamed", "command": "printf"})
        renamed_parsed = parse_source(adapter, renamed, Path("settings.jsonc"))
        self.assertNotIn("alpha", renamed_parsed["servers"])
        self.assertEqual(renamed_parsed["servers"]["renamed"]["command"], "printf")
        self.assertIn('"keep": true', renamed)

    def test_json_nested_secret_fields_merge_without_replacing_unknown_values(self):
        adapter = adapter_by_id("gemini")
        source = '{\n  "mcpServers": {\n    "alpha": {\n      "command": "echo",\n      "environment": {\n        "KEEP": "unchanged",\n        // retain this note\n        "TOKEN": "$TOKEN"\n      }\n    }\n  }\n}\n'
        changed = patch_source(adapter, source, Path("settings.jsonc"), action="upsert-server", name="alpha", payload={"env": {"ADDED": "$ADDED"}})
        parsed = parse_source(adapter, changed, Path("settings.jsonc"))
        self.assertEqual(parsed["servers"]["alpha"]["environment"]["KEEP"], "unchanged")
        self.assertEqual(parsed["servers"]["alpha"]["environment"]["ADDED"], "$ADDED")
        self.assertIn("// retain this note", changed)

    def test_codex_table_family_edit(self):
        source = 'title = "keep"\n\n[mcp_servers."alpha.name"]\n# keep server comment\ncommand = "echo"\nargs = ["one"]\n\n[mcp_servers."alpha.name".env]\nTOKEN = "$TOKEN"\n\n[other]\nvalue = 1\n'
        adapter = adapter_by_id("codex")
        changed = patch_source(adapter, source, Path("config.toml"), action="set-enabled", name="alpha.name", payload={"enabled": False})
        self.assertIn('title = "keep"', changed)
        self.assertIn("[other]", changed)
        self.assertIn("# keep server comment", changed)
        self.assertIn("enabled = false", changed)
        parse_toml(changed)
        self.assertEqual(changed, (Path(__file__).parent / "golden/toml-toggle.golden").read_bytes().decode("utf-8"))

        crlf = '[mcp_servers."x"]\r\n# keep\r\ncommand = "echo"\r\n'
        crlf_changed = patch_source(adapter, crlf, Path("config.toml"), action="set-enabled", name="x", payload={"enabled": False})
        self.assertNotIn("\n", crlf_changed.replace("\r\n", ""))
        self.assertIn("# keep\r\n", crlf_changed)

    def test_codex_rename_duplicate_and_quoted_environment_keys(self):
        adapter = adapter_by_id("codex")
        source = '[mcp_servers."alpha"] # root note\n# command note\ncommand = "echo"\n\n[mcp_servers."alpha".env]\nKEEP = "unchanged"\n\n[mcp_servers."taken"]\ncommand = "printf"\n'
        with self.assertRaises(TomlSourceError):
            patch_source(adapter, source, Path("config.toml"), action="duplicate-server", name="alpha", payload={"name": "taken", "command": "echo"})
        renamed = patch_source(adapter, source, Path("config.toml"), action="upsert-server", name="alpha", payload={"name": "renamed", "command": "echo", "env": {"API.KEY": "$API_KEY"}})
        parsed = parse_toml(renamed)
        self.assertNotIn("alpha", parsed["mcp_servers"])
        self.assertEqual(parsed["mcp_servers"]["renamed"]["env"]["KEEP"], "unchanged")
        self.assertEqual(parsed["mcp_servers"]["renamed"]["env"]["API.KEY"], "$API_KEY")
        self.assertIn("# root note", renamed)
        self.assertIn("# command note", renamed)

    def test_generic_import_dispatches_by_extension(self):
        generic = adapter_by_id("generic")
        parsed_json = parse_source(generic, '{"mcpServers":{"x":{"command":"echo"}}}', Path("import.json"))
        parsed_toml = parse_source(generic, '[mcp_servers."x"]\ncommand = "echo"\n', Path("import.toml"))
        self.assertEqual(parsed_json["format"], "json")
        self.assertEqual(parsed_toml["format"], "toml")

    def test_secret_safe_normalization(self):
        adapter = adapter_by_id("gemini")
        parsed = parse_source(adapter, '{"mcpServers":{"x":{"command":"echo","env":{"API_KEY":"real-secret-value","MODE":"dev"},"url":"https://example.test/mcp?token=real-secret-value"}}}', Path("settings.json"))
        server = normalized_servers(adapter, parsed, "src_test")[0]
        rendered = repr(server)
        self.assertNotIn("real-secret-value", rendered)
        self.assertIn("API_KEY", rendered)
        self.assertIn("set", rendered)

    def test_inline_secret_flags_are_never_rendered(self):
        _, args = redact_command("tool", ["--api-key=fixture-short", "--token", "fixture-next", "--mode", "safe"])
        rendered = " ".join(args)
        self.assertNotIn("fixture-short", rendered)
        self.assertNotIn("fixture-next", rendered)
        self.assertIn("<secret hidden>", rendered)

    def test_malformed_urls_commands_and_names_are_redacted(self):
        secret = "fixture-short-secret"
        rendered_url = repr(redact_url("relative/path?token=" + secret))
        self.assertNotIn(secret, rendered_url)
        command, args = redact_command("tool --password=" + secret, ["mode=ok", "token=" + secret])
        self.assertNotIn(secret, repr((command, args)))
        secret_name = "s" + "k-" + "secretvalue99"
        server = normalized_server(secret_name, {"command": "echo", "cwd": "/tmp/token=" + secret})
        self.assertNotIn(secret_name, repr(server))
        self.assertNotIn(secret, repr(server))
        self.assertNotIn(secret, repr(response_safe({"message": "token=" + secret, secret_name: "value"})))

    def test_conversion_preview_is_explicitly_lossy_and_secret_safe(self):
        server = {"name": "remote", "transport": "sse", "url": {"display": "https://example.test/mcp?token=<redacted>", "state": "set"}, "headers": [{"name": "Authorization", "state": "set"}], "environment": []}
        preview = conversion_preview(server, "codex")
        self.assertTrue(preview["lossy"])
        self.assertTrue(any("secret" in warning.lower() or "header" in warning.lower() for warning in preview["warnings"]))
        self.assertNotIn("real", repr(preview))

    def test_conversion_batch_reports_partial_failure_without_aborting(self):
        server = {"name": "local", "transport": "stdio", "command": "echo", "args": [], "environment": [], "headers": []}
        preview = conversion_batch_preview(server, ["codex", "not-an-adapter"])
        self.assertEqual(len(preview["results"]), 1)
        self.assertEqual(len(preview["failures"]), 1)
        self.assertTrue(preview["partialFailure"])

    def test_comparison_matrix_has_agent_columns(self):
        result = comparison({"agents": [{"id": "codex", "name": "Codex", "sources": [{"sourceId": "s", "servers": [{"name": "alpha", "enabled": True, "transport": "stdio"}]}]}]})
        self.assertEqual(result["serverNames"], ["alpha"])
        self.assertEqual(result["agents"][0]["servers"]["alpha"]["state"], "enabled")

    def test_import_authorization_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            imported = root / "import.json"
            imported.write_text('{"mcpServers":{"imported":{"command":"echo"}}}\n', encoding="utf-8")
            old = {key: os.environ.get(key) for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")}
            try:
                os.environ.update({"HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "home/.config"), "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"), "XDG_RUNTIME_DIR": str(root / "run")})
                _register(str(imported), "generic", "read")
                result = scan()
                generic = next(agent for agent in result["agents"] if agent["id"] == "generic")
                self.assertFalse(generic["sources"][0]["writable"])
                _forget(generic["sources"][0]["sourceId"])
                self.assertFalse(any(agent["id"] == "generic" for agent in scan()["agents"]))
                _register(str(imported), "generic", "manage")
                result = scan()
                generic = next(agent for agent in result["agents"] if agent["id"] == "generic")
                self.assertTrue(generic["sources"][0]["managed"])
                self.assertTrue(generic["sources"][0]["writable"])
                _forget(generic["sources"][0]["sourceId"])
                _register(str(imported), "gemini", "manage")
                result = scan()
                source = next(source for agent in result["agents"] for source in agent["sources"] if source["pathDisplay"].endswith("import.json"))
                self.assertTrue(source["managed"])
                self.assertTrue(source["writable"])
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

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
