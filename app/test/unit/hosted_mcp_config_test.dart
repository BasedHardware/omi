import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/mcp_config.dart';

void main() {
  group('hostedMcpUrl', () {
    test('joins the canonical /v1/mcp path onto a base without a trailing slash', () {
      expect(hostedMcpUrl('https://api.omi.me'), 'https://api.omi.me/v1/mcp');
    });

    test('normalizes one or many trailing slashes', () {
      expect(hostedMcpUrl('https://api.omi.me/'), 'https://api.omi.me/v1/mcp');
      expect(hostedMcpUrl('https://api.omi.me///'), 'https://api.omi.me/v1/mcp');
    });

    test('never advertises the legacy /v1/mcp/sse alias', () {
      expect(hostedMcpUrl('https://api.omi.me/'), isNot(contains('sse')));
    });
  });

  group('hostedMcpConfigJson', () {
    const url = 'https://api.omi.me/v1/mcp';

    test('is valid hosted Streamable HTTP config for Claude Code', () {
      final decoded = jsonDecode(hostedMcpConfigJson(url)) as Map<String, dynamic>;
      final omi = (decoded['mcpServers'] as Map<String, dynamic>)['omi'] as Map<String, dynamic>;
      expect(omi['type'], 'http');
      expect(omi['url'], url);
      expect(omi['headers'], {'Authorization': 'Bearer <key>'});
      expect(omi.containsKey('command'), isFalse);
    });

    test('embeds the given canonical URL and no docker transport', () {
      final text = hostedMcpConfigJson('https://dev.example.com/v1/mcp');
      expect(text, contains('"url": "https://dev.example.com/v1/mcp"'));
      expect(text, isNot(contains('docker')));
      expect(text, isNot(contains('mcp-remote')));
    });

    test('stays parseable for a configured base containing quotes or backslashes', () {
      const oddBase = 'https://odd"example\\.com/';
      final mcpUrl = hostedMcpUrl(oddBase);
      final decoded = jsonDecode(hostedMcpConfigJson(mcpUrl)) as Map<String, dynamic>;
      final omi = (decoded['mcpServers'] as Map<String, dynamic>)['omi'] as Map<String, dynamic>;
      expect(omi['url'], mcpUrl);
      // Highlighted view and copied text still agree byte-for-byte.
      final rebuilt = hostedMcpConfigTokens(mcpUrl).map((token) => token.$2).join();
      expect(rebuilt, hostedMcpConfigJson(mcpUrl));
    });
  });

  test('highlighted tokens rebuild the exact copied config text', () {
    const url = 'https://api.omi.me/v1/mcp';
    final rebuilt = hostedMcpConfigTokens(url).map((token) => token.$2).join();
    expect(rebuilt, hostedMcpConfigJson(url));
  });

  test('the Claude OAuth connector uses the registered prod client id', () {
    expect(kMcpOAuthClientId, 'omi-claude-prod');
  });
}
