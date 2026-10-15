import 'package:flutter/material.dart';
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

/// Switching Light/Dark from a page opened on the Settings sheet, then going back, left the sheet on
/// the old surface under rows and header drawn in the new palette (black sheet behind white rows
/// in Light, and the reverse in Dark), because the route's background colour was fixed when the
/// sheet opened. The root below mirrors main.dart: the palette follows [AppearanceProvider], the
/// theme follows `themeMode`, and the navigator is re-keyed by brightness.

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

Color _sheetSurface(WidgetTester tester) => tester
    .widget<Material>(find.descendant(of: find.byType(BottomSheet), matching: find.byType(Material)).first)
    .color!;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'givenName': 'Ada', 'email': 'ada@example.com', 'uid': 'uid-1234567'});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi',
      packageName: 'com.friend.ios',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
  });
  tearDown(() => OmiColors.active = OmiPalette.dark);

  Future<AppearanceProvider> pumpApp(WidgetTester tester, {required ThemeMode start, required String open}) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final appearance = AppearanceProvider(read: () => start.name, write: (_) async {});
    // One key for the app's life, like MyApp.navigatorKey, so re-keying by brightness moves the navigator.
    final navigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
          ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage()),
          ChangeNotifierProvider<CaptureProvider>(create: (_) => _Capture()),
          ChangeNotifierProvider<AppearanceProvider>.value(value: appearance),
        ],
        builder: (context, _) {
          final mode = context.watch<AppearanceProvider>().mode;
          final brightness = resolveAppearanceBrightness(mode, Brightness.dark);
          OmiColors.active = OmiColors.forBrightness(brightness);
          return MaterialApp(
            navigatorKey: navigatorKey,
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            locale: const Locale('en'),
            theme: buildOmiTheme(brightness: Brightness.light),
            darkTheme: buildOmiTheme(brightness: Brightness.dark),
            themeMode: mode,
            builder: (context, child) => KeyedSubtree(key: ValueKey(brightness), child: child!),
            home: Builder(
              builder: (context) => Scaffold(
                body: TextButton(
                  onPressed: () => open == 'settings'
                      ? SettingsDrawer.show(context)
                      : showOmiSheet<void>(context: context, title: 'Sheet', builder: (_) => const Text('Body')),
                  child: const Text('Open'),
                ),
              ),
            ),
          );
        },
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    return appearance;
  }

  testWidgets('the open Settings sheet repaints its surface when the appearance changes', (tester) async {
    final appearance = await pumpApp(tester, start: ThemeMode.dark, open: 'settings');
    expect(find.byType(SettingsDrawer), findsOneWidget);
    expect(_sheetSurface(tester), OmiPalette.dark.surface0);

    await appearance.setMode(ThemeMode.light);
    await tester.pumpAndSettle();
    expect(find.byType(SettingsDrawer), findsOneWidget, reason: 'the sheet stays open across the switch');
    expect(_sheetSurface(tester), OmiPalette.light.surface0);

    await appearance.setMode(ThemeMode.dark);
    await tester.pumpAndSettle();
    expect(_sheetSurface(tester), OmiPalette.dark.surface0);
  });

  testWidgets('an open showOmiSheet follows the appearance on surface1', (tester) async {
    final appearance = await pumpApp(tester, start: ThemeMode.light, open: 'sheet');
    expect(find.text('Body'), findsOneWidget);
    expect(_sheetSurface(tester), OmiPalette.light.surface1);

    await appearance.setMode(ThemeMode.dark);
    await tester.pumpAndSettle();
    expect(_sheetSurface(tester), OmiPalette.dark.surface1);
  });
}
