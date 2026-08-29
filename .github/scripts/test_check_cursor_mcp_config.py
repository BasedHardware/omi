#!/usr/bin/env python3

from __future__ import annotations

import copy
import unittest

from check_cursor_mcp_config import (
    CONFIG_PATH,
    PLAYWRIGHT_PACKAGE,
    config_errors,
    load_config,
)


class CursorMCPConfigContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(CONFIG_PATH)

    def test_repository_config_satisfies_contract(self) -> None:
        self.assertEqual(config_errors(self.config), [])

    def test_rejects_each_package_identity_from_issue_12376(self) -> None:
        old_packages = {
            "github": "@modelcontextprotocol/server-github",
            "notion": "@modelcontextprotocol/server-notion",
            "figma": "@modelcontextprotocol/server-figma",
            "browser": "@modelcontextprotocol/server-browser",
        }

        for server_name, package in old_packages.items():
            with self.subTest(server=server_name):
                mutated = copy.deepcopy(self.config)
                mutated["mcpServers"][server_name] = {
                    "command": "npx",
                    "args": ["-y", package],
                }
                self.assertTrue(
                    any(
                        f"unsupported MCP package {package}" in error
                        for error in config_errors(mutated)
                    )
                )

    def test_rejects_floating_npx_package(self) -> None:
        self.config["mcpServers"]["browser"]["args"] = ["-y", "@playwright/mcp@latest"]
        errors = config_errors(self.config)
        self.assertIn(
            "browser must pin its npx package to an exact semantic version", errors
        )
        self.assertIn(
            f"browser must use Microsoft's pinned {PLAYWRIGHT_PACKAGE} server", errors
        )

    def test_rejects_remote_endpoint_downgrade(self) -> None:
        self.config["mcpServers"]["notion"]["url"] = "http://mcp.notion.com/mcp"
        errors = config_errors(self.config)
        self.assertIn("notion.url must use HTTPS", errors)
        self.assertIn(
            "notion must use its maintained provider endpoint and authentication contract",
            errors,
        )

    def test_rejects_plaintext_credential(self) -> None:
        self.config["mcpServers"]["github"]["headers"][
            "Authorization"
        ] = "Bearer secret-value"
        errors = config_errors(self.config)
        self.assertIn(
            "github.headers.Authorization must use a ${env:NAME} reference, not a committed value",
            errors,
        )

    def test_rejects_credentials_forwarded_to_browser_process(self) -> None:
        self.config["mcpServers"]["browser"]["env"] = {"API_TOKEN": "${env:API_TOKEN}"}
        self.assertIn(
            "browser MCP must not receive repository credentials",
            config_errors(self.config),
        )


if __name__ == "__main__":
    unittest.main()
