import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/ui/ui.dart';
import '../support/test_browser.dart';

void main() {
  late TestBrowser browser;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    browser = TestBrowser()..install();
  });
  tearDown(() => browser.dispose());

  Future<void> pump(WidgetTester tester, AddMcpServerPage page) async {
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: page));
    await tester.enterText(find.byType(TextFormField).at(0), 'Synthetic MCP');
    await tester.enterText(find.byType(TextFormField).at(2), 'https://mcp.example.test/mcp');
    await tester.pump();
  }

  testWidgets('hung MCP status stops waiting and a retry reuses the existing server registration', (tester) async {
    var creates = 0;
    var reads = 0;
    final first = Completer<Map<String, dynamic>?>();
    await pump(
        tester,
        AddMcpServerPage(
            addServer: (name, url, {description}) async {
              creates++;
              return {'app_id': 'mcp-1', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth'};
            },
            appDetailsLoader: (_) {
              reads++;
              return reads == 1 ? first.future : Future.value({'status': 'pending_mcp_auth'});
            },
            probeTimeout: const Duration(seconds: 1),
            waitTimeout: const Duration(seconds: 5)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(creates, 1);
    expect(browser.launches.single, ('https://provider.test/auth', false, false));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).onPressed, isNotNull);
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(creates, 1);
    expect(reads, 2);
    await tester.pumpWidget(const SizedBox());
    first.complete({'status': 'approved'});
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('malformed MCP creation never claims success and releases the button', (tester) async {
    await pump(tester, AddMcpServerPage(addServer: (name, url, {description}) async => {'requires_oauth': false}));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    expect(find.byType(AddMcpServerPage), findsOneWidget);
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).isLoading, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('leaving MCP authorization cancels pending probes and navigation', (tester) async {
    final read = Completer<Map<String, dynamic>?>();
    await pump(
        tester,
        AddMcpServerPage(
            addServer: (name, url, {description}) async =>
                {'app_id': 'mcp-1', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth'},
            appDetailsLoader: (_) => read.future));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    read.complete({'status': 'approved'});
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a late direct MCP detail cannot navigate into another account', (tester) async {
    final read = Completer<Map<String, dynamic>?>();
    SharedPreferencesUtil().uid = 'first-account';
    await pump(
        tester,
        AddMcpServerPage(
            addServer: (name, url, {description}) async => {'app_id': 'mcp-1', 'requires_oauth': false},
            appDetailsLoader: (_) => read.future));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    SharedPreferencesUtil().uid = 'next-account';
    read.complete({
      'id': 'mcp-1',
      'name': 'Synthetic MCP',
      'author': 'Omi',
      'description': 'Fixture',
      'image': '',
      'capabilities': <String>[],
      'category': 'utilities',
      'status': 'approved',
      'enabled': true,
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(AddMcpServerPage), findsOneWidget);
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).isLoading, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('MCP connection waits for the server enable receipt after approval', (tester) async {
    var approved = false;
    var enabled = false;
    Map<String, dynamic> data() => {
          'id': 'mcp-1',
          'name': 'Synthetic MCP',
          'author': 'Omi',
          'description': 'Fixture',
          'image': '',
          'capabilities': <String>[],
          'status': approved ? 'approved' : 'pending_mcp_auth',
          'category': 'utilities',
          'approved': true,
          'rating_count': 0,
          'enabled': enabled,
          'deleted': false,
          'is_paid': false,
          'is_user_paid': false
        };
    final provider = AppProvider()..appDetailsOverride = (_) async => data();
    addTearDown(provider.dispose);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<AppProvider>.value(value: provider),
          ChangeNotifierProvider<AddAppProvider>(create: (_) => AddAppProvider()),
          ChangeNotifierProvider<MessageProvider>(create: (_) => MessageProvider()),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: AddMcpServerPage(
                addServer: (name, url, {description}) async =>
                    {'app_id': 'mcp-1', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth'},
                appDetailsLoader: (_) async => data()))));
    await tester.enterText(find.byType(TextFormField).at(0), 'Synthetic MCP');
    await tester.enterText(find.byType(TextFormField).at(2), 'https://mcp.example.test/mcp');
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 200));
    await tester.pump();
    approved = true;
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
    expect(find.byType(AddMcpServerPage), findsOneWidget, reason: 'Approval is not an enable receipt');
    enabled = true;
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump();
    expect(find.byType(AppDetailPage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
