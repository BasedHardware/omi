import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

/// Settings on the screens and settings people actually use: the smallest and largest iPhones,
/// large accessibility text, and languages whose words run long (German), use another script
/// (Russian, Japanese, Hindi) or read right to left (Arabic). Any layout overflow fails the test.
/// Also pins the Settings typeface: Instrument Sans on the Settings pages, not elsewhere.

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  bool get isConnected => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Usage extends ChangeNotifier implements UsageProvider {
  @override
  UserSubscriptionResponse? get subscription => null;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get hasNativeBackgroundStreamRoute => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// The top-level rows that open a page of rows.
const _groupRows = [
  'settings_account',
  'settings_group_device',
  'settings_group_recording',
  'settings_group_notifications',
  'settings_group_privacy',
  'settings_group_help',
];

const _iPhoneSE1 = Size(320, 568);
const _iPhoneSE = Size(375, 667);
const _iPhoneProMax = Size(430, 932);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'givenName': 'Maximiliana Alexandra Featherstonehaugh-Montgomery',
      'email': 'maximiliana.featherstonehaugh@a-very-long-company-domain.example.com',
      'uid': 'uid-1234567',
    });
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi',
      packageName: 'com.friend.ios',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
  });

  Future<void> pumpSettings(WidgetTester tester,
      {required Size size, double textScale = 1, String locale = 'en'}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
          ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage()),
          ChangeNotifierProvider<CaptureProvider>(create: (_) => _Capture()),
          ChangeNotifierProvider<AppearanceProvider>(create: (_) => AppearanceProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: Locale(locale),
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
          home: const SettingsDrawer(),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  /// Scrolls the page top to bottom, then opens every group page and does the same there.
  Future<void> walkSettings(WidgetTester tester) async {
    Future<void> scrollThrough() async {
      final scrollable = find.byType(Scrollable).first;
      for (var i = 0; i < 12; i++) {
        await tester.drag(scrollable, const Offset(0, -400));
        await tester.pump();
      }
      await tester.pumpAndSettle();
    }

    await scrollThrough();
    for (final key in _groupRows) {
      final row = find.byKey(ValueKey(key));
      await tester.dragUntilVisible(row, find.byType(Scrollable).first, const Offset(0, 300));
      await tester.pumpAndSettle();
      await tester.tap(row);
      await tester.pumpAndSettle();
      expect(find.byType(OmiGroupedPage), findsOneWidget, reason: '$key opens its page');
      await scrollThrough();
      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();
    }
  }

  for (final (name, size) in [
    ('iPhone SE 1st gen', _iPhoneSE1),
    ('iPhone SE', _iPhoneSE),
    ('Pro Max', _iPhoneProMax)
  ]) {
    for (final scale in [1.0, 1.5, 2.0]) {
      testWidgets('$name at ${scale}x text: every Settings page lays out', (tester) async {
        await pumpSettings(tester, size: size, textScale: scale);
        await walkSettings(tester);
      });
    }
  }

  for (final locale in ['de', 'ru', 'ja', 'hi', 'ar']) {
    testWidgets('$locale on an iPhone SE at 1.5x text: every Settings page lays out', (tester) async {
      await pumpSettings(tester, size: _iPhoneSE, textScale: 1.5, locale: locale);
      await walkSettings(tester);
    });
  }

  testWidgets('Settings text is set in Instrument Sans', (tester) async {
    await pumpSettings(tester, size: _iPhoneSE);
    final en = lookupAppLocalizations(const Locale('en'));
    String? familyOf(Finder text) => tester.renderObject<RenderParagraph>(text).text.style?.fontFamily;
    expect(familyOf(find.text(en.settings)), OmiSettingsTypeface.family);
    expect(familyOf(find.text(en.planAndUsage)), OmiSettingsTypeface.family);

    // A group page (an OmiGroupedPage) carries it too.
    await tester.tap(find.byKey(const ValueKey('settings_group_recording')));
    await tester.pumpAndSettle();
    expect(familyOf(find.text(en.language)), OmiSettingsTypeface.family);
  });
}
