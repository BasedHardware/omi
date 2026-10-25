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
  final reauthorized = <String>[];
  Future<String?> reauthorize(String appId) async {
    reauthorized.add(appId);
    return 'https://provider.test/fresh-$appId-${reauthorized.length}';
  }

  setUp(() async {
    reauthorized.clear();
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
            authorizeServer: reauthorize,
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

  testWidgets('a URL edited while registration is pending never reuses the earlier server', (tester) async {
    final created = <String>[];
    final first = Completer<Map<String, dynamic>?>();
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) {
              created.add(url);
              return created.length == 1
                  ? first.future
                  : Future.value(
                      {'app_id': 'mcp-b', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth-b'});
            },
            appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
            probeTimeout: const Duration(seconds: 1),
            waitTimeout: const Duration(seconds: 5)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.enterText(find.byType(TextFormField).at(2), 'https://other.example.test/mcp');
    first.complete({'app_id': 'mcp-a', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth-a'});
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(browser.launches, isEmpty, reason: "server A's authorization never opens for the URL B now in the form");

    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(created, ['https://mcp.example.test/mcp', 'https://other.example.test/mcp'], reason: 'B is registered');
    expect(browser.launches.single.$1, 'https://provider.test/auth-b');
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('editing the URL while waiting on a server stops that wait and registers the new one', (tester) async {
    final created = <String>[];
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async {
              created.add(url);
              final id = created.length == 1 ? 'a' : 'b';
              return {'app_id': 'mcp-$id', 'requires_oauth': true, 'auth_url': 'https://provider.test/auth-$id'};
            },
            appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
            probeTimeout: const Duration(seconds: 1),
            waitTimeout: const Duration(seconds: 30)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(browser.launches.map((l) => l.$1), ['https://provider.test/auth-a']);

    await tester.enterText(find.byType(TextFormField).at(2), 'https://other.example.test/mcp');
    await tester.pump();
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(created, ['https://mcp.example.test/mcp', 'https://other.example.test/mcp']);
    expect(browser.launches.map((l) => l.$1), ['https://provider.test/auth-a', 'https://provider.test/auth-b']);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  Map<String, dynamic> oauthRegistration(String id) =>
      {'app_id': id, 'requires_oauth': true, 'auth_url': 'https://provider.test/auth-$id'};

  Future<void> editUrl(WidgetTester tester, String url) async {
    await tester.enterText(find.byType(TextFormField).at(2), url);
    await tester.pump();
  }

  testWidgets('a URL edited while the browser launch is pending never polls the earlier server', (tester) async {
    final reads = <String>[];
    browser.pending = Completer<bool>();
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async => oauthRegistration('server-a'),
            appDetailsLoader: (id) async {
              reads.add(id);
              return {'status': 'pending_mcp_auth'};
            },
            probeTimeout: const Duration(seconds: 1),
            waitTimeout: const Duration(seconds: 5)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(browser.launches.map((l) => l.$1), ['https://provider.test/auth-server-a']);

    await editUrl(tester, 'https://other.example.test/mcp');
    browser.pending!.complete(true);
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));

    expect(reads, isEmpty, reason: 'the form shows B; nothing may poll A');
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).onPressed, isNotNull);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('a cached-registration retry retires with its URL while the browser launch is pending', (tester) async {
    var creates = 0;
    final reads = <String>[];
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async {
              creates++;
              return oauthRegistration('server-a');
            },
            appDetailsLoader: (id) async {
              reads.add(id);
              return {'status': 'pending_mcp_auth'};
            },
            probeTimeout: const Duration(milliseconds: 200),
            waitTimeout: const Duration(seconds: 1)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
    final readsAfterFirstWait = reads.length;
    expect(readsAfterFirstWait, greaterThan(0));

    browser.pending = Completer<bool>();
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    expect(creates, 1, reason: 'the retry reuses the registration made for this URL');
    expect(browser.launches, hasLength(2));

    await editUrl(tester, 'https://other.example.test/mcp');
    browser.pending!.complete(true);
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));

    expect(reads.length, readsAfterFirstWait, reason: 'the retired retry must not start polling');
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('a URL edited while the direct detail read is pending never navigates', (tester) async {
    final read = Completer<Map<String, dynamic>?>();
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async => {'app_id': 'server-a', 'requires_oauth': false},
            appDetailsLoader: (_) => read.future));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump(const Duration(milliseconds: 100));

    await editUrl(tester, 'https://other.example.test/mcp');
    read.complete({
      'id': 'server-a',
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
    expect(find.byType(AppDetailPage), findsNothing);
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).isLoading, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('returning A to B to A does not resurrect the old attempt; an explicit retry reuses A', (tester) async {
    var creates = 0;
    final reads = <String>[];
    browser.pending = Completer<bool>();
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async {
              creates++;
              return oauthRegistration('server-a');
            },
            appDetailsLoader: (id) async {
              reads.add(id);
              return {'status': 'pending_mcp_auth'};
            },
            probeTimeout: const Duration(seconds: 1),
            waitTimeout: const Duration(seconds: 5)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await editUrl(tester, 'https://other.example.test/mcp');
    await editUrl(tester, 'https://mcp.example.test/mcp');
    browser.pending!.complete(true);
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    expect(reads, isEmpty, reason: 'the first attempt was retired by the edit, not paused');

    browser.pending = null;
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(creates, 1, reason: 'the registration stays keyed to URL A');
    expect(reads, ['server-a'], reason: 'the explicit retry owns A and polls it');
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  Map<String, dynamic> appData(String id, {required bool enabled, String status = 'approved'}) => {
        'id': id,
        'name': 'Synthetic MCP',
        'author': 'Omi',
        'description': 'Fixture',
        'image': '',
        'capabilities': <String>[],
        'status': status,
        'category': 'utilities',
        'approved': true,
        'rating_count': 0,
        'enabled': enabled,
        'deleted': false,
        'is_paid': false,
        'is_user_paid': false
      };

  Future<void> pumpWithProviders(WidgetTester tester, AddMcpServerPage page, AppProvider provider) async {
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<AppProvider>.value(value: provider),
          ChangeNotifierProvider<AddAppProvider>(create: (_) => AddAppProvider()),
          ChangeNotifierProvider<MessageProvider>(create: (_) => MessageProvider()),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: page)));
    await tester.enterText(find.byType(TextFormField).at(0), 'Synthetic MCP');
    await tester.enterText(find.byType(TextFormField).at(2), 'https://mcp.example.test/mcp');
    await tester.pump();
  }

  testWidgets('an approved server without OAuth reaches its Enable action without claiming it is connected',
      (tester) async {
    final provider = AppProvider()..appDetailsOverride = (_) async => appData('server-a', enabled: false);
    addTearDown(provider.dispose);
    await pumpWithProviders(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) async => {'app_id': 'server-a', 'requires_oauth': false},
            appDetailsLoader: (_) async => appData('server-a', enabled: false)),
        provider);
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump();
    expect(find.byType(AppDetailPage), findsOneWidget, reason: 'the detail page owns Enable');
    expect(find.textContaining('connected successfully'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  for (final lateWhile in ['browser launch', 'status wait']) {
    testWidgets('a late registration A never replaces or cancels B while its $lateWhile is pending', (tester) async {
      final registrations = <String, Completer<Map<String, dynamic>?>>{};
      final reads = <String>[];
      var bEnabled = false;
      final provider = AppProvider()..appDetailsOverride = (id) async => appData(id, enabled: true);
      addTearDown(provider.dispose);
      await pumpWithProviders(
          tester,
          AddMcpServerPage(
              authorizeServer: reauthorize,
              addServer: (name, url, {description}) => (registrations[url] = Completer<Map<String, dynamic>?>()).future,
              appDetailsLoader: (id) async {
                reads.add(id);
                return appData(id, enabled: bEnabled, status: bEnabled ? 'approved' : 'pending_mcp_auth');
              },
              probeTimeout: const Duration(seconds: 1),
              waitTimeout: const Duration(seconds: 30)),
          provider);
      await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
      await tester.pump();
      await editUrl(tester, 'https://other.example.test/mcp');
      await tester.pump(const Duration(milliseconds: 600));
      if (lateWhile == 'browser launch') browser.pending = Completer<bool>();
      await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
      await tester.pump();
      registrations['https://other.example.test/mcp']!.complete(oauthRegistration('server-b'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      registrations['https://mcp.example.test/mcp']!.complete(oauthRegistration('server-a'));
      await tester.pump();
      browser.pending?.complete(true);
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      expect(browser.launches.map((l) => l.$1), ['https://provider.test/auth-server-b']);
      expect(reads.toSet(), {'server-b'}, reason: 'only B is polled, and A did not cancel its wait');

      bEnabled = true;
      await tester.pump(const Duration(seconds: 3));
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump();
      expect(find.byType(AppDetailPage), findsOneWidget, reason: 'B completes normally');
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('a late registration A stays cached for an explicit retry on URL A', (tester) async {
    final created = <String>[];
    final first = Completer<Map<String, dynamic>?>();
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) {
              created.add(url);
              return created.length == 1 ? first.future : Future.value(oauthRegistration('server-b'));
            },
            appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
            probeTimeout: const Duration(milliseconds: 200),
            waitTimeout: const Duration(seconds: 1)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await editUrl(tester, 'https://other.example.test/mcp');
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    first.complete(oauthRegistration('server-a'));
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    await editUrl(tester, 'https://mcp.example.test/mcp');
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(created, hasLength(2), reason: 'URL A reuses its registration');
    expect(reauthorized, ['server-a'], reason: 'its retry asks for fresh authorization of registration A');
    expect(browser.launches.map((l) => l.$1).last, 'https://provider.test/fresh-server-a-1');
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('a late first registration never replaces the newer same-URL registration', (tester) async {
    final first = Completer<Map<String, dynamic>?>();
    var registrations = 0;
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize,
            addServer: (name, url, {description}) {
              registrations++;
              return registrations == 1 ? first.future : Future.value(oauthRegistration('new-registration'));
            },
            appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
            probeTimeout: const Duration(milliseconds: 100),
            waitTimeout: const Duration(milliseconds: 300)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await editUrl(tester, 'https://other.example.test/mcp');
    await editUrl(tester, 'https://mcp.example.test/mcp');
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    first.complete(oauthRegistration('old-registration'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(registrations, 2);
    expect(reauthorized, ['new-registration'], reason: 'the retry belongs to the newer registration');
    expect(browser.launches.map((l) => l.$1).last, 'https://provider.test/fresh-new-registration-1');
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('a retry never reopens the original single-use authorization', (tester) async {
    var creates = 0;
    String? Function(String) authorizer = (id) => 'https://provider.test/fresh-$id';
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: (id) async {
              reauthorized.add(id);
              return authorizer(id);
            },
            addServer: (name, url, {description}) async {
              creates++;
              return oauthRegistration('server-a');
            },
            appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
            probeTimeout: const Duration(milliseconds: 100),
            waitTimeout: const Duration(milliseconds: 300)));
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 600));
    // The first state was consumed or expired: the retry gets a new one for the same registration.
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(creates, 1);
    expect(browser.launches.map((l) => l.$1),
        ['https://provider.test/auth-server-a', 'https://provider.test/fresh-server-a']);
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 600));
    // If fresh authorization is unavailable, nothing is launched and the user sees the failure.
    authorizer = (_) => null;
    await tester.tap(find.widgetWithText(OmiButton, 'Connect'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(browser.launches, hasLength(2), reason: 'never falls back to the consumed URL');
    expect(tester.widget<OmiButton>(find.widgetWithText(OmiButton, 'Connect')).onPressed, isNotNull,
        reason: 'a failed authorization releases Connect for another retry');
    expect(reauthorized, ['server-a', 'server-a']);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  testWidgets('a slow fresh authorization holds Connect so a second press cannot rotate it', (tester) async {
    final authorization = Completer<String?>();
    var authorizations = 0;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: AddMcpServerPage(
        addServer: (name, url, {description}) async =>
            {'app_id': 'synthetic-app', 'requires_oauth': true, 'auth_url': 'https://provider.test/initial'},
        authorizeServer: (_) {
          authorizations++;
          return authorization.future;
        },
        appDetailsLoader: (_) async => {'status': 'pending_mcp_auth'},
        probeTimeout: const Duration(milliseconds: 100),
        waitTimeout: const Duration(milliseconds: 300),
      ),
    ));
    await tester.enterText(find.byType(TextFormField).at(0), 'Synthetic MCP');
    await tester.enterText(find.byType(TextFormField).at(2), 'https://mcp.example.test/mcp');
    await tester.pump();
    final connect = find.widgetWithText(OmiButton, 'Connect');
    await tester.tap(connect);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(connect);
    await tester.pump();
    expect(authorizations, 1);
    await tester.pump(const Duration(milliseconds: 600));
    await tester.tap(connect);
    await tester.pump();
    final observed = authorizations;
    authorization.complete(null);
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
    expect(observed, 1, reason: 'a slow authorization must disable Connect until it settles');
  });

  testWidgets('malformed MCP creation never claims success and releases the button', (tester) async {
    await pump(
        tester,
        AddMcpServerPage(
            authorizeServer: reauthorize, addServer: (name, url, {description}) async => {'requires_oauth': false}));
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
            authorizeServer: reauthorize,
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
            authorizeServer: reauthorize,
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
                authorizeServer: reauthorize,
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
