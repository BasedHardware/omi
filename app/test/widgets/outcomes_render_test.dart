import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/settings/notifications_settings_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Renders the new §17 Outcomes failure states on an iPhone-sized screen with the app's real fonts
/// and asserts each lays out without overflow. With
/// `--dart-define=OUTCOMES_RENDER_OUTPUT=<dir>` it also writes the PNGs used as PR evidence.
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
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

/// On a phone, text with no family (the app bar title, the toast message) uses the system font; the
/// test engine's default is a placeholder face, so the evidence theme names SF Pro for it.
ThemeData _evidenceTheme() {
  final theme = buildOmiTheme(brightness: Brightness.dark);
  return theme.copyWith(
    appBarTheme: theme.appBarTheme.copyWith(
      titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
    snackBarTheme: theme.snackBarTheme.copyWith(
      contentTextStyle: theme.snackBarTheme.contentTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
  );
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  int get batteryLevel => 90;

  @override
  bool get isCharging => false;

  @override
  void setOnFirmwareUpdatePage(bool value) {}

  @override
  void resetFirmwareUpdateState() {}

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Unreadable extends NotificationSettingsApi {
  const _Unreadable();

  @override
  Future<DailySummarySettings?> dailySummary() async => null;

  @override
  Future<MentorNotificationSettings?> mentor() async => null;
}

void main() {
  const output = String.fromEnvironment('OUTCOMES_RENDER_OUTPUT');
  final boundary = GlobalKey();

  setUpAll(_loadFonts);
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'render-user'});
    await SharedPreferencesUtil.init();
  });

  Future<void> shoot(WidgetTester tester, String name) async {
    expect(tester.takeException(), isNull, reason: '$name rendered with an exception');
    if (output.isNotEmpty) {
      await tester.runAsync(() async {
        final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
      });
    }
    debugDefaultTargetPlatformOverride = null;
  }

  Future<void> pump(WidgetTester tester, Widget home, {List<ChangeNotifierProvider> providers = const []}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    final app = MaterialApp(
      navigatorKey: globalNavigatorKey,
      debugShowCheckedModeBanner: false,
      theme: _evidenceTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: home,
    );
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: providers.isEmpty ? app : MultiProvider(providers: providers, child: app),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('D1 firmware check with no answer', (tester) async {
    debugLatestFirmwareLookup = ({
      required deviceModelNumber,
      required firmwareRevision,
      required hardwareRevision,
      required manufacturerName,
      serialNumber,
    }) async =>
        null;
    addTearDown(() => debugLatestFirmwareLookup = null);
    await pump(
      tester,
      FirmwareUpdate(
        device: BtDevice(
          id: 'd',
          name: 'Omi',
          type: DeviceType.omi,
          rssi: -40,
          modelNumber: 'Omi DevKit 2',
          firmwareRevision: '3.0.0',
          hardwareRevision: '1',
          manufacturerName: 'Based Hardware',
        ),
      ),
      providers: [ChangeNotifierProvider<DeviceProvider>.value(value: _Device())],
    );
    expect(find.byKey(const Key('firmware_check_failed')), findsOneWidget);
    await shoot(tester, '001-mobile-ios-firmware-check-failed');
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
  });

  testWidgets('P4 notification settings that could not be read', (tester) async {
    await pump(tester, const NotificationsSettingsPage(api: _Unreadable(), showLiveActivity: false));
    expect(find.byKey(const Key('notification_settings_load_failed')), findsOneWidget);
    await shoot(tester, '002-mobile-ios-notification-settings-unread');
  });

  testWidgets('G2 goal sheet after a failed save', (tester) async {
    await pump(
      tester,
      Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: TextButton(
              onPressed: () => showGoalFormSheet(
                context,
                goal: Goal(
                  id: 'a',
                  title: 'Read 12 books',
                  goalType: 'numeric',
                  targetValue: 12,
                  currentValue: 3,
                  minValue: 0,
                  maxValue: 12,
                  isActive: true,
                  createdAt: DateTime.utc(2026, 9, 1),
                  updatedAt: DateTime.utc(2026, 9, 1),
                ),
                onSave: (title, current, target, emoji) async => false,
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('goal_save_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byKey(const Key('goal_save_failed')), findsOneWidget, reason: 'said inside the sheet, not under it');
    await shoot(tester, '003-mobile-ios-goal-save-failed');
  });
}
