import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/services/agent_connect/zkr_share.dart';
import 'package:omi/ui/ui.dart';

const fakeAgentLink = 'https://zkr.scalingforever.com/a/AbCdEfGhIjKlMnOpQrStUv#v1.KEYKEYKEY.TOKENTOKEN';

/// An in-memory backend for the Connect an Agent screens: grants, keys, and a zkr link that never
/// leaves the process.
class FakeAgentBackend {
  FakeAgentBackend({
    this.chatGptConnected = false,
    Map<String, DateTime?> keys = const {},
    this.failLoad = false,
    this.chatGptScopes,
  }) : keys = {
          for (final entry in keys.entries)
            'key-${entry.key}': McpApiKey.fromJson({
              'id': 'key-${entry.key}',
              'name': '${entry.key} (Omi app)',
              'key_prefix': 'omi_mcp_ab',
              'created_at': '2026-10-14T09:00:00Z',
              if (entry.value != null) 'last_used_at': entry.value!.toUtc().toIso8601String(),
            }),
        };

  bool chatGptConnected;
  bool failLoad;

  /// Scopes on the ChatGPT grant; null leaves them off the record.
  List<String>? chatGptScopes;

  /// When set, the zkr link is held until it completes.
  Completer<void>? holdShare;
  final Map<String, McpApiKey> keys;
  final created = <String>[];
  final revokedKeys = <String>[];
  final revokedGrants = <String>[];

  AgentConnectService service() => AgentConnectService(
        apiBase: 'https://api.omi.me/',
        loadGrants: () async {
          if (failLoad) throw Exception('offline');
          return [
            if (chatGptConnected)
              {
                'id': 'grant-chatgpt',
                'status': 'active',
                'client_id': 'omi-chatgpt-prod',
                if (chatGptScopes != null) 'scopes': chatGptScopes
              },
          ];
        },
        revokeGrant: (id) async {
          revokedGrants.add(id);
          chatGptConnected = false;
        },
        loadKeys: () async => keys.values.toList(),
        createKey: (name) async {
          created.add(name);
          final id = 'key-new-${created.length}';
          keys[id] = McpApiKey.fromJson({
            'id': id,
            'name': name,
            'key_prefix': 'omi_mcp_ab',
            'created_at': '2026-10-16T12:00:00Z',
          });
          return McpApiKeyCreated.fromJson({
            'id': id,
            'name': name,
            'key': 'omi_mcp_secret',
            'key_prefix': 'omi_mcp_ab',
            'created_at': '2026-10-16T12:00:00Z',
          });
        },
        deleteKey: (id) async {
          revokedKeys.add(id);
          keys.remove(id);
        },
        share: (_) async {
          await holdShare?.future;
          return const ZkrShare(id: 'AbCdEfGhIjKlMnOpQrStUv', agentLink: fakeAgentLink);
        },
      );
}

Widget connectAgentHost(Widget home, {Brightness brightness = Brightness.dark}) {
  OmiColors.active = OmiColors.forBrightness(brightness);
  return MaterialApp(
    theme: buildOmiTheme(brightness: brightness),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: home,
  );
}

/// Records what the screens put on the clipboard.
List<String> captureClipboard(WidgetTester tester) {
  final copied = <String>[];
  OmiClipboard.debugSystemConfirmsCopy = false;
  addTearDown(() => OmiClipboard.debugSystemConfirmsCopy = null);
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
    return null;
  });
  addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
  return copied;
}

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void usePhoneViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}
