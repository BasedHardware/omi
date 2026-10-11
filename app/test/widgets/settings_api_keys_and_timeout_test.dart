import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/conversation_timeout_dialog.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/providers/mcp_provider.dart';

class _FakeMcpProvider extends McpProvider {
  final deleted = <String>[];

  @override
  Future<void> deleteKey(String keyId) async => deleted.add(keyId);
}

class _FakeDevApiKeyProvider extends DevApiKeyProvider {
  final deleted = <String>[];

  @override
  Future<void> deleteKey(String keyId) async => deleted.add(keyId);
}

Widget _app(Widget child) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    locale: const Locale('en'),
    home: Scaffold(body: child),
  );
}

/// The Revoke button inside the confirmation dialog (the row's own Revoke is behind it).
Finder _dialogRevoke() => find.descendant(of: find.byType(AlertDialog), matching: find.text('Revoke'));

void main() {
  final createdAt = DateTime(2026, 9, 23, 10, 43);

  testWidgets('revoking an MCP key asks first; Cancel keeps it, Revoke deletes it', (tester) async {
    final provider = _FakeMcpProvider();
    await tester.pumpWidget(
      _app(
        ChangeNotifierProvider<McpProvider>.value(
          value: provider,
          child: McpApiKeyListItem(
            apiKey: McpApiKey(createdAt: createdAt, id: 'mcp-1', keyPrefix: 'omi_mcp_ab', name: 'Claude'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Revoke'));
    await tester.pumpAndSettle();
    expect(find.text('Revoke Key?'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(provider.deleted, isEmpty);

    await tester.tap(find.text('Revoke'));
    await tester.pumpAndSettle();
    await tester.tap(_dialogRevoke());
    await tester.pumpAndSettle();
    expect(provider.deleted, ['mcp-1']);
  });

  testWidgets('a developer key shows a localized date and confirms before revoking', (tester) async {
    final provider = _FakeDevApiKeyProvider();
    await tester.pumpWidget(
      _app(
        ChangeNotifierProvider<DevApiKeyProvider>.value(
          value: provider,
          child: DevApiKeyListItem(
            apiKey: DevApiKey(
              createdAt: createdAt,
              id: 'dev-1',
              keyPrefix: 'omi_dev_ab',
              name: 'Script',
              scopes: const ['memories:read'],
            ),
          ),
        ),
      ),
    );

    expect(find.textContaining('Sep 23, 2026'), findsOneWidget);
    expect(find.text('Read'), findsOneWidget);

    await tester.tap(find.text('Revoke'));
    await tester.pumpAndSettle();
    await tester.tap(_dialogRevoke());
    await tester.pumpAndSettle();
    expect(provider.deleted, ['dev-1']);
  });

  testWidgets('the conversation timeout picker applies the tapped option and closes', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().conversationSilenceDuration = 120;

    await tester.pumpWidget(
      _app(
        Builder(
          builder: (context) => TextButton(
            onPressed: () => ConversationTimeoutDialog.show(context),
            child: const Text('open'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Conversation Timeout'), findsOneWidget);

    await tester.tap(find.text('10 minutes'));
    await tester.pumpAndSettle();

    expect(SharedPreferencesUtil().conversationSilenceDuration, 600);
    expect(find.text('10 minutes'), findsNothing);
  });

  for (final platform in [TargetPlatform.android, TargetPlatform.iOS]) {
    testWidgets('the create-MCP-key dialog takes a name on ${platform.name} and enables Create', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(platform: platform),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('en'),
          home: ChangeNotifierProvider<McpProvider>.value(
            value: _FakeMcpProvider(),
            child: Builder(
              builder: (context) => TextButton(
                onPressed: () => showDialog(context: context, builder: (_) => const CreateMcpApiKeyDialog()),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      await tester.enterText(find.byType(TextField), 'Claude Desktop');
      await tester.pump();
      expect(find.text('Claude Desktop'), findsOneWidget);

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.byType(CreateMcpApiKeyDialog), findsNothing);
    });
  }
}
