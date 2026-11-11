import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/first_value.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/first_value_recovery_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

const output = String.fromEnvironment('FIRST_VALUE_RECOVERY_RENDER_OUTPUT');
final _boundary = GlobalKey();

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto',
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

Future<void> _mountHome(WidgetTester tester) async {
  PromptQueue.instance.reset();
  AnalyticsManager.resetForTesting();
  AnalyticsManager().bindIdentity('synthetic-owner');
  FirstValueRecoveryService.instance.debugNotificationPermission = () async => true;
  FirstValueRecoveryService.instance.debugTimeZone = () async => 'UTC';
  addTearDown(() {
    PromptQueue.instance.reset();
    AnalyticsManager.resetForTesting();
    FirstValueRecoveryService.instance.debugNotificationPermission = null;
    FirstValueRecoveryService.instance.debugTimeZone = null;
  });
  await tester.pumpWidget(MaterialApp(
    navigatorKey: globalNavigatorKey,
    theme: buildOmiTheme(brightness: Brightness.dark),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: const Scaffold(body: SizedBox.expand()),
  ));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await _loadFonts();
  });

  for (final kind in ['capture', 'result']) {
    testWidgets('paid start $kind recovery dialog uses the real prompt path', (
      tester,
    ) async {
      final capture = kind == 'capture';
      final route = capture ? '/settings/device' : '/conversation/result-1';
      var requests = 0;
      var preparations = 0;
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      addTearDown(PromptQueue.instance.reset);
      addTearDown(AnalyticsManager.resetForTesting);
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      AnalyticsManager.resetForTesting();
      AnalyticsManager().bindIdentity('synthetic-owner');
      final identityEpoch = AnalyticsManager.identityEpoch;
      FirstValueRecoveryService.instance.debugApi = FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (request) async {
          if (request.url.endsWith('/prepare')) {
            expect(request.headers[FirstValueApi.protocolHeader], '1');
            expect(request.headers[FirstValueApi.permissionHeader], 'granted');
            expect(request.headers[FirstValueApi.timeZoneHeader], 'UTC');
            preparations++;
            return http.Response('{"ready":true}', 200);
          }
          requests++;
          expect(request.headers[FirstValueApi.protocolHeader], '1');
          expect(request.headers[FirstValueApi.permissionHeader], 'granted');
          expect(request.headers[FirstValueApi.timeZoneHeader], 'UTC');
          return http.Response(
            jsonEncode({
              'prompt': {'kind': kind, 'channel': 'in_app', 'route': route}
            }),
            200,
          );
        },
      );
      FirstValueRecoveryService.instance.debugNotificationPermission = () async => true;
      FirstValueRecoveryService.instance.debugTimeZone = () async => 'UTC';
      addTearDown(() {
        FirstValueRecoveryService.instance.debugNotificationPermission = null;
        FirstValueRecoveryService.instance.debugTimeZone = null;
      });

      await tester.pumpWidget(
        RepaintBoundary(
          key: _boundary,
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            navigatorKey: globalNavigatorKey,
            theme: buildOmiTheme(brightness: Brightness.dark),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const Scaffold(body: SizedBox.expand()),
          ),
        ),
      );
      PromptQueue.instance.blocked = () => true;
      await tester.runAsync(FirstValueRecoveryService.instance.checkOnAppOpen);
      await tester.pump();
      expect(preparations, 1);
      expect(requests, 0, reason: 'A blocked prompt must not consume a server claim');
      PromptQueue.instance.blocked = () => false;
      await tester.runAsync(() async {
        PromptQueue.instance.pump();
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await tester.pump();
      await tester.pumpAndSettle();

      final title = capture ? 'Device Not Connected' : 'Summary generated';
      final button = capture ? 'Connect Device' : 'Open';
      expect(find.text(title), findsOneWidget);
      expect(requests, 1);
      expect(find.text(button), findsOneWidget);
      expect(tester.takeException(), isNull);
      if (output.isNotEmpty) {
        await tester.runAsync(() async {
          final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await render.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory(output).create(recursive: true);
          await File(
            '$output/${capture ? '001-mobile-ios-first-value-recovery' : '002-mobile-ios-first-value-ready'}.png',
          ).writeAsBytes(bytes!.buffer.asUint8List());
        });
      }

      final opened = <String>[];
      Future<bool> opener(String route, {bool Function()? canOpen}) async {
        opened.add(route);
        return true;
      }

      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));
      await tester.tap(find.text(button));
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pumpAndSettle();
      expect(find.text(title), findsNothing);
      expect(PromptQueue.instance.showingId, isNull);
      expect(tester.takeException(), isNull);
      expect(AnalyticsManager.identityEpoch, identityEpoch);
      expect(opened, [route]);
      debugDefaultTargetPlatformOverride = null;
    });
  }

  for (final outcome in ['empty', '404', 'failed', 'malformed', 'timeout']) {
    testWidgets('deferred $outcome preparation never blocks an existing prompt', (tester) async {
      await _mountHome(tester);
      final lookup = Completer<http.Response>();
      final paths = <String>[];
      FirstValueRecoveryService.instance.debugApi = FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (request) {
          paths.add(Uri.parse(request.url).path);
          return lookup.future;
        },
      );
      final checking = FirstValueRecoveryService.instance.checkOnAppOpen();
      await tester.pump();
      expect(paths, ['/v1/first-value/recovery/prepare']);
      expect(PromptQueue.instance.pendingIds, isEmpty);
      expect(PromptQueue.instance.showingId, isNull);
      var existingShown = false;
      final existing = Completer<void>();
      PromptQueue.instance.enqueue('existing-announcement', PromptPriority.normal, show: (_) async {
        existingShown = true;
        await existing.future;
      });
      await tester.pump();
      expect(existingShown, isTrue, reason: 'Existing prompts run while optional HTTP is unresolved');
      expect(PromptQueue.instance.showingId, 'existing-announcement');
      if (outcome == 'timeout') {
        await tester.pump(const Duration(seconds: 16));
      } else if (outcome == 'failed') {
        lookup.completeError(const SocketException('offline fixture'));
      } else {
        lookup.complete(http.Response(
          outcome == 'empty' ? '{"ready":false}' : (outcome == 'malformed' ? '[]' : '{}'),
          outcome == '404' ? 404 : 200,
        ));
      }
      await tester.pump();
      await checking;
      expect(paths, ['/v1/first-value/recovery/prepare'], reason: 'No fallback to the consumptive route');
      expect(PromptQueue.instance.pendingIds, isEmpty);
      expect(PromptQueue.instance.showingId, 'existing-announcement');
      existing.complete();
      if (!lookup.isCompleted) lookup.complete(http.Response('{"ready":true}', 200));
      await tester.pumpAndSettle();
      expect(PromptQueue.instance.showingId, isNull);
      expect(PromptQueue.instance.pendingIds, isEmpty, reason: 'Late readiness after timeout is ignored');
    });
  }

  for (final phase in ['preparation', 'queued', 'claim', 'unmounted']) {
    testWidgets('identity switch during $phase cannot display or claim stale work', (tester) async {
      await _mountHome(tester);
      final lookup = Completer<http.Response>();
      final claim = Completer<http.Response>();
      var claims = 0;
      FirstValueRecoveryService.instance.debugApi = FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (request) {
          if (request.url.endsWith('/prepare')) return lookup.future;
          claims++;
          return claim.future;
        },
      );
      PromptQueue.instance.blocked = () => phase == 'queued';
      final checking = FirstValueRecoveryService.instance.checkOnAppOpen();
      await tester.pump();
      if (phase == 'preparation') AnalyticsManager().bindIdentity('other-owner');
      lookup.complete(http.Response('{"ready":true}', 200));
      await tester.pump();
      await checking;
      if (phase != 'preparation' && phase != 'unmounted') AnalyticsManager().bindIdentity('other-owner');
      if (phase == 'unmounted') await tester.pumpWidget(const SizedBox());
      if (phase == 'queued') {
        expect(claims, 0);
        PromptQueue.instance.blocked = () => false;
        PromptQueue.instance.pump();
      }
      if (phase == 'claim' || phase == 'unmounted') {
        expect(claims, 1);
        claim.complete(http.Response('{"prompt":{"kind":"capture","route":"/settings/device"}}', 200));
      }
      await tester.pumpAndSettle();
      expect(claims, phase == 'claim' || phase == 'unmounted' ? 1 : 0);
      expect(find.text('Device Not Connected'), findsNothing);
      expect(PromptQueue.instance.pendingIds, isEmpty, reason: 'Stale queue entries drain without claiming');
      expect(PromptQueue.instance.showingId, isNull);
    });
  }

  testWidgets('higher priority prompt retains the queue before any first-value claim', (tester) async {
    await _mountHome(tester);
    var claims = 0;
    FirstValueRecoveryService.instance.debugApi = FirstValueApi(
      baseUrl: 'https://fixture.invalid/',
      send: (request) async {
        if (request.url.endsWith('/prepare')) return http.Response('{"ready":true}', 200);
        claims++;
        return http.Response('{"prompt":null}', 200);
      },
    );
    PromptQueue.instance.blocked = () => true;
    await FirstValueRecoveryService.instance.checkOnAppOpen();
    final higher = Completer<void>();
    PromptQueue.instance.enqueue('existing-safety', PromptPriority.high, show: (_) => higher.future);
    PromptQueue.instance.blocked = () => false;
    PromptQueue.instance.pump();
    await tester.pump();
    expect(PromptQueue.instance.showingId, 'existing-safety');
    expect(claims, 0);
    higher.complete();
    await tester.pumpAndSettle();
    expect(claims, 1);
    expect(PromptQueue.instance.showingId, isNull);
  });

  testWidgets('global hold starting during claim suppresses display', (tester) async {
    await _mountHome(tester);
    final claim = Completer<http.Response>();
    var claims = 0;
    FirstValueRecoveryService.instance.debugApi = FirstValueApi(
      baseUrl: 'https://fixture.invalid/',
      send: (request) {
        if (request.url.endsWith('/prepare')) return Future.value(http.Response('{"ready":true}', 200));
        claims++;
        return claim.future;
      },
    );
    await FirstValueRecoveryService.instance.checkOnAppOpen();
    await tester.pump();
    expect(claims, 1);
    PromptQueue.instance.blocked = () => true;
    claim.complete(http.Response('{"prompt":{"kind":"capture","route":"/settings/device"}}', 200));
    await tester.pumpAndSettle();
    expect(find.text('Device Not Connected'), findsNothing);
    expect(PromptQueue.instance.showingId, isNull);
  });
}
