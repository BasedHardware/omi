import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/referral/referral_page.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';

import '../../support/test_browser.dart';

void main() {
  late TestBrowser browser;
  setUpAll(() async {
    final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
    for (final family in manifest) {
      final loader = FontLoader(family['family'] as String);
      for (final font in family['fonts'] as List) {
        loader.addFont(rootBundle.load(font['asset'] as String));
      }
      await loader.load();
    }
    var directory = File(Platform.resolvedExecutable).parent;
    for (var i = 0; i < 8; i++) {
      final fonts = Directory('${directory.path}/material_fonts');
      if (File('${fonts.path}/Roboto-Regular.ttf').existsSync()) {
        // Unstyled controls use the test default Ahem; give that fallback
        // Android's real Roboto glyphs as well as its explicit font family.
        for (final family in ['Roboto', 'Ahem']) {
          final loader = FontLoader(family);
          for (final weight in ['Regular', 'Medium', 'Bold']) {
            loader.addFont(
                Future.value(ByteData.sublistView(File('${fonts.path}/Roboto-$weight.ttf').readAsBytesSync())));
          }
          await loader.load();
        }
        break;
      }
      directory = directory.parent;
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    browser = TestBrowser();
    browser.install();
  });
  tearDown(() => browser.dispose());

  Future<void> pumpPage(WidgetTester tester, Widget page) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final previousPalette = OmiColors.active;
    OmiColors.active = OmiPalette.dark;
    addTearDown(() => OmiColors.active = previousPalette);
    await tester.pumpWidget(RepaintBoundary(
      key: const Key('hanging-evidence'),
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme().copyWith(platform: TargetPlatform.android),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: page,
      ),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> evidence(WidgetTester tester, String name) async {
    final path = Platform.environment['OMI_ANDROID_HANGS_EVIDENCE_DIR'];
    if (path == null) return;
    await tester.runAsync(() async {
      final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const Key('hanging-evidence')));
      final image = await boundary.toImage(pixelRatio: 2);
      final data = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(path).create(recursive: true);
      await File('$path/$name.png').writeAsBytes(data!.buffer.asUint8List());
      image.dispose();
    });
  }

  testWidgets('referral opens outside WebView and exposes a retry if launch fails', (tester) async {
    browser.opened = false;
    await pumpPage(tester, const ReferralPage());
    expect(browser.launches.single, ('https://affiliate.omi.me/', false, false));
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.byType(OmiSpinner), findsNothing);
    await evidence(tester, '001-mobile-android-referral-retry');
    browser.opened = true;
    await tester.tap(find.text('Try Again'));
    await tester.pumpAndSettle();
    expect(browser.launches, hasLength(2));
    expect(find.text('Please complete authentication in your browser. Once done, return to the app.'), findsOneWidget);
    await evidence(tester, '002-mobile-android-referral-browser');
    await tester.tap(find.byKey(const Key('referral-open-browser')));
    await tester.pumpAndSettle();
    expect(browser.launches, hasLength(3));
    expect(tester.takeException(), isNull);
  });

  testWidgets('failed task status offers retry and only a fresh server reply confirms connection', (tester) async {
    TaskIntegrationsResponse? reply;
    final provider = TaskIntegrationProvider(fetchStatus: () async => reply);
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester, ChangeNotifierProvider.value(value: provider, child: const TaskIntegrationsPage()));
    expect(provider.hasLoadError, isTrue);
    expect(find.text('Try Again'), findsNWidgets(4));
    await evidence(tester, '003-mobile-android-integration-retry');
    reply = TaskIntegrationsResponse(integrations: {
      'todoist': {'app_key': 'todoist', 'connected': true}
    }, defaultApp: 'todoist');
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    expect(provider.hasLoadError, isFalse);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    expect(find.text('Try Again'), findsNothing);
  });

  testWidgets('starting OAuth does not change default until a resumed read verifies the grant', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = TaskIntegrationProvider(
      fetchStatus: () async => TaskIntegrationsResponse(
          integrations: connected
              ? {
                  'todoist': {'app_key': 'todoist', 'connected': true}
                }
              : {}),
      setDefaultTaskIntegrationFn: (key) async {
        defaults.add(key);
        return true;
      },
    );
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (app) async => true)));
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(defaults, isEmpty);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isFalse);
    await evidence(tester, '004-mobile-android-integration-auth-pending');
    connected = true;
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(defaults, ['todoist']);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    expect(provider.selectedApp, TaskIntegrationApp.todoist);
    expect(tester.takeException(), isNull);
  });
  testWidgets('a grant saved after returning from Google is adopted without another manual action', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = TaskIntegrationProvider(
        fetchStatus: () async => TaskIntegrationsResponse(
            integrations: connected
                ? {
                    'todoist': {'app_key': 'todoist', 'connected': true}
                  }
                : {}),
        setDefaultTaskIntegrationFn: (key) async {
          defaults.add(key);
          return true;
        });
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) async => true)));
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(defaults, isEmpty);
    connected = true;
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(defaults, ['todoist']);
    expect(provider.selectedApp, TaskIntegrationApp.todoist);
  });

  testWidgets('a status read that answers inside its own 45s budget still completes authorization', (tester) async {
    var authorized = false;
    final defaults = <String>[];
    final provider = TaskIntegrationProvider(fetchStatus: () async {
      if (!authorized) return TaskIntegrationsResponse(integrations: {});
      await Future<void>.delayed(const Duration(seconds: 30)); // slower than the old 20s probe
      return TaskIntegrationsResponse(integrations: {
        'todoist': {'app_key': 'todoist', 'connected': true}
      });
    }, setDefaultTaskIntegrationFn: (key) async {
      defaults.add(key);
      return true;
    });
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) async => true)));
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    authorized = true;
    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(seconds: 31));
    await tester.pumpAndSettle();
    expect(defaults, ['todoist']);
    expect(provider.selectedApp, TaskIntegrationApp.todoist);
  });

  testWidgets('choosing another task app retires the earlier pending authorization selection', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = TaskIntegrationProvider(
        fetchStatus: () async => TaskIntegrationsResponse(integrations: {
              'asana': {'app_key': 'asana', 'connected': true},
              if (connected) 'todoist': {'app_key': 'todoist', 'connected': true},
            }),
        setDefaultTaskIntegrationFn: (key) async {
          defaults.add(key);
          return true;
        });
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) async => true)));
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Asana'));
    await tester.pumpAndSettle();
    expect(defaults, ['asana']);
    connected = true;
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(defaults, ['asana']);
    expect(provider.selectedApp, TaskIntegrationApp.asana);
    await tester.pumpWidget(const SizedBox());
  });

  TaskIntegrationProvider asanaConnectedProvider(List<String> defaults, bool Function() todoistConnected) {
    final provider = TaskIntegrationProvider(
        fetchStatus: () async => TaskIntegrationsResponse(integrations: {
              'asana': {'app_key': 'asana', 'connected': true},
              if (todoistConnected()) 'todoist': {'app_key': 'todoist', 'connected': true},
            }),
        setDefaultTaskIntegrationFn: (key) async {
          defaults.add(key);
          return true;
        });
    provider.clearUserData();
    return provider;
  }

  Future<void> startTodoist(WidgetTester tester) async {
    await tester.tap(find.text('Todoist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pump();
  }

  testWidgets('a newer selection while authorization is still starting retires the older attempt', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = asanaConnectedProvider(defaults, () => connected);
    addTearDown(provider.dispose);
    final launch = Completer<bool>();
    await pumpPage(
        tester,
        ChangeNotifierProvider.value(
            value: provider,
            child: TaskIntegrationsPage(
                authenticate: (app) => app == TaskIntegrationApp.todoist ? launch.future : Future.value(true))));
    await startTodoist(tester); // the browser launch result is still outstanding
    await tester.tap(find.text('Asana'));
    await tester.pumpAndSettle();
    expect(defaults, ['asana']);

    connected = true;
    launch.complete(true); // the earlier Todoist launch reports late
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(defaults, ['asana'], reason: 'the retired Todoist attempt never saves a default');
    expect(provider.selectedApp, TaskIntegrationApp.asana);
    expect(find.text('Try Again'), findsNothing, reason: 'no pending authorization is resurrected');
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a launch receipt after the page closes does nothing', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = asanaConnectedProvider(defaults, () => connected);
    addTearDown(provider.dispose);
    final launch = Completer<bool>();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) => launch.future)));
    await startTodoist(tester);
    await tester.pumpWidget(const SizedBox());
    connected = true;
    launch.complete(true);
    await tester.pump(const Duration(seconds: 3));
    expect(defaults, isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a launch receipt after an account change does nothing for the new account', (tester) async {
    var connected = false;
    final defaults = <String>[];
    final provider = asanaConnectedProvider(defaults, () => connected);
    addTearDown(provider.dispose);
    SharedPreferencesUtil().uid = 'account-a';
    final launch = Completer<bool>();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) => launch.future)));
    await startTodoist(tester);
    SharedPreferencesUtil().uid = 'account-b';
    connected = true;
    launch.complete(true);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(defaults, isEmpty, reason: "account A's authorization never selects for account B");
    expect(find.text('Try Again'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a launch that throws leaves the next selection free to start', (tester) async {
    final defaults = <String>[];
    final provider = asanaConnectedProvider(defaults, () => false);
    addTearDown(provider.dispose);
    var launches = 0;
    await pumpPage(
        tester,
        ChangeNotifierProvider.value(
            value: provider,
            child: TaskIntegrationsPage(authenticate: (_) async {
              launches++;
              if (launches == 1) throw StateError('browser unavailable');
              return true;
            })));
    await startTodoist(tester);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await startTodoist(tester);
    await tester.pumpAndSettle();
    expect(launches, 2, reason: 'a thrown launch must not leave authorization stuck as starting');
    expect(find.text('Try Again'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('choosing Asana while a Todoist default save is pending keeps Asana', (tester) async {
    final writes = <String>[];
    final pending = <String, Completer<bool>>{};
    final provider = TaskIntegrationProvider(
        fetchStatus: () async => TaskIntegrationsResponse(integrations: {
              'asana': {'app_key': 'asana', 'connected': true},
              'todoist': {'app_key': 'todoist', 'connected': true},
            }),
        setDefaultTaskIntegrationFn: (key) {
          writes.add(key);
          return (pending[key] = Completer<bool>()).future;
        });
    addTearDown(provider.dispose);
    provider.clearUserData();
    await pumpPage(tester,
        ChangeNotifierProvider.value(value: provider, child: TaskIntegrationsPage(authenticate: (_) async => true)));
    await tester.tap(find.text('Todoist'));
    await tester.pump();
    await tester.tap(find.text('Asana'));
    await tester.pump();
    if (pending['asana'] != null) pending['asana']!.complete(true);
    pending['todoist']!.complete(true);
    await tester.pump();
    if (pending['asana']?.isCompleted == false) pending['asana']!.complete(true);
    await tester.pumpAndSettle();

    expect(writes.last, 'asana', reason: 'the server ends on the latest choice');
    expect(provider.selectedApp, TaskIntegrationApp.asana);
    await tester.pumpWidget(const SizedBox());
  });
}
