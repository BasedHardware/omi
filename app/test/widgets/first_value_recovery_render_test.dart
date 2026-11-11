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
import 'package:omi/ui/prompts/prompt_queue.dart';
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await _loadFonts();
  });

  testWidgets('paid start capture recovery dialog uses the real prompt path', (
    tester,
  ) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
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
        expect(request.headers[FirstValueApi.protocolHeader], '1');
        expect(request.headers[FirstValueApi.permissionHeader], 'granted');
        expect(request.headers[FirstValueApi.timeZoneHeader], 'UTC');
        return http.Response(
          '{"prompt":{"kind":"capture","channel":"in_app","route":"/settings/device"}}',
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
    await tester.runAsync(FirstValueRecoveryService.instance.checkOnAppOpen);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Device Not Connected'), findsOneWidget);
    expect(find.text('Connect Device'), findsOneWidget);
    expect(tester.takeException(), isNull);
    if (output.isNotEmpty) {
      await tester.runAsync(() async {
        final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File(
          '$output/001-mobile-ios-first-value-recovery.png',
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
    await tester.tap(find.text('Connect Device'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(find.text('Device Not Connected'), findsNothing);
    expect(PromptQueue.instance.showingId, isNull);
    expect(tester.takeException(), isNull);
    expect(AnalyticsManager.identityEpoch, identityEpoch);
    expect(opened, ['/settings/device']);
    debugDefaultTargetPlatformOverride = null;
  });
}
