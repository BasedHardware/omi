import 'dart:convert';

// Pure helpers for the hosted MCP surface (Streamable HTTP).
// Flutter-free so settings UI and tests share the same values.

/// Canonical hosted MCP endpoint path appended to the API base URL.
const String kMcpEndpointPath = '/v1/mcp';

/// OAuth Client ID registered for Claude's advanced connector settings.
const String kMcpOAuthClientId = 'omi-claude-prod';

/// Segment kinds for the syntax-highlighted Claude config block.
enum McpJsonToken { plain, key, string }

/// Canonical hosted MCP URL derived from [apiBaseUrl], with trailing slashes
/// normalized away so the endpoint is always joined exactly once.
String hostedMcpUrl(String apiBaseUrl) => '${apiBaseUrl.replaceAll(RegExp(r'/+$'), '')}$kMcpEndpointPath';

/// Ordered JSON segments of the Claude Code `~/.claude.json` `mcpServers`
/// entry. The copyable text and the highlighted code block are both built
/// from this single source so they can never drift apart.
List<(McpJsonToken, String)> hostedMcpConfigTokens(String mcpUrl) => [
      (McpJsonToken.plain, '{\n  '),
      (McpJsonToken.key, '"mcpServers"'),
      (McpJsonToken.plain, ': {\n    '),
      (McpJsonToken.key, '"omi"'),
      (McpJsonToken.plain, ': {\n      '),
      (McpJsonToken.key, '"type"'),
      (McpJsonToken.plain, ': '),
      (McpJsonToken.string, '"http"'),
      (McpJsonToken.plain, ',\n      '),
      (McpJsonToken.key, '"url"'),
      (McpJsonToken.plain, ': '),
      // jsonEncode keeps the output parseable even for an odd configured base.
      (McpJsonToken.string, jsonEncode(mcpUrl)),
      (McpJsonToken.plain, ',\n      '),
      (McpJsonToken.key, '"headers"'),
      (McpJsonToken.plain, ': {\n        '),
      (McpJsonToken.key, '"Authorization"'),
      (McpJsonToken.plain, ': '),
      (McpJsonToken.string, '"Bearer <key>"'),
      (McpJsonToken.plain, '\n      }\n    }\n  }\n}'),
    ];

/// The exact Claude Code `~/.claude.json` config JSON copied to the clipboard.
String hostedMcpConfigJson(String mcpUrl) => hostedMcpConfigTokens(mcpUrl).map((token) => token.$2).join();
