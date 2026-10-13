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
}
