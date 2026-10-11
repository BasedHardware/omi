import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/ui/omi_tokens.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the palette starts light before the appearance provider resolves', () {
    // The app is light until someone picks Dark or System; the first frame must not flash dark.
    expect(OmiColors.active, OmiPalette.light);
  });

  test('appearance preference defaults to Light and round trips', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final prefs = SharedPreferencesUtil();
    expect(AppearanceProvider.parse(prefs.appearanceMode), ThemeMode.light);

    await prefs.setAppearanceMode('system');
    expect(AppearanceProvider.parse(prefs.appearanceMode), ThemeMode.system);
    expect((await SharedPreferences.getInstance()).getString(SharedPreferencesUtil.appearanceModeKey), 'system');
    await prefs.setAppearanceMode('unexpected');
    expect(AppearanceProvider.parse(prefs.appearanceMode), ThemeMode.light);
  });

  test('provider notifies on a change and persists its value', () async {
    var stored = 'invalid';
    final provider = AppearanceProvider(read: () => stored, write: (value) async => stored = value);
    addTearDown(provider.dispose);
    var notifications = 0;
    provider.addListener(() => notifications++);
    expect(provider.mode, ThemeMode.light);
    await provider.setMode(ThemeMode.dark);
    expect(provider.mode, ThemeMode.dark);
    expect(stored, 'dark');
    expect(notifications, 1);
    await provider.setMode(ThemeMode.dark);
    expect(notifications, 1);
  });

  test('selecting the displayed default persists it without notifying', () async {
    var stored = 'invalid';
    var writes = 0;
    final provider = AppearanceProvider(
      read: () => stored,
      write: (value) async {
        stored = value;
        writes++;
      },
    );
    addTearDown(provider.dispose);
    var notifications = 0;
    provider.addListener(() => notifications++);

    await provider.setMode(ThemeMode.light);

    expect(stored, 'light');
    expect(writes, 1);
    expect(notifications, 0);
  });

  test('both themes use the corresponding palette', () {
    final light = buildOmiTheme(brightness: Brightness.light);
    final dark = buildOmiTheme(brightness: Brightness.dark);
    expect(light.brightness, Brightness.light);
    expect(light.scaffoldBackgroundColor, const Color(0xFFF2F2F7));
    expect(light.colorScheme.primary, Colors.black);
    expect(light.colorScheme.onPrimary, Colors.white);
    expect(light.appBarTheme.systemOverlayStyle, SystemUiOverlayStyle.dark);
    expect(dark.brightness, Brightness.dark);
    expect(dark.scaffoldBackgroundColor, Colors.black);
    expect(dark.colorScheme.primary, Colors.white);
    expect(dark.appBarTheme.systemOverlayStyle, SystemUiOverlayStyle.light);
  });

  test('System follows either OS brightness', () {
    expect(resolveAppearanceBrightness(ThemeMode.system, Brightness.light), Brightness.light);
    expect(resolveAppearanceBrightness(ThemeMode.system, Brightness.dark), Brightness.dark);
    expect(resolveAppearanceBrightness(ThemeMode.light, Brightness.dark), Brightness.light);
    expect(resolveAppearanceBrightness(ThemeMode.dark, Brightness.light), Brightness.dark);
  });

  testWidgets('Settings picker updates the theme and visible value without a restart', (tester) async {
    final provider = AppearanceProvider(read: () => 'dark', write: (_) async {});
    addTearDown(provider.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<AppearanceProvider>.value(
      value: provider,
      child: Consumer<AppearanceProvider>(builder: (context, appearance, _) {
        final brightness = resolveAppearanceBrightness(appearance.mode, Brightness.dark);
        OmiColors.active = OmiColors.forBrightness(brightness);
        return MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(brightness: Brightness.light),
          darkTheme: buildOmiTheme(brightness: Brightness.dark),
          themeMode: appearance.mode,
          home: const NotificationsDisplayGroupPage(),
        );
      }),
    ));
    expect(Theme.of(tester.element(find.byType(NotificationsDisplayGroupPage))).brightness, Brightness.dark);
    await tester.tap(find.byKey(const ValueKey('settings_row_appearance')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Light').last);
    await tester.pumpAndSettle();
    expect(provider.mode, ThemeMode.light);
    expect(Theme.of(tester.element(find.byType(NotificationsDisplayGroupPage))).brightness, Brightness.light);
    expect(find.text('Light'), findsOneWidget);
    OmiColors.active = OmiPalette.dark;
  });

  testWidgets('appearance rebuild keeps the current route', (tester) async {
    final provider = AppearanceProvider(read: () => 'dark', write: (_) async {});
    final navigatorKey = GlobalKey<NavigatorState>();
    addTearDown(provider.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<AppearanceProvider>.value(
      value: provider,
      child: Consumer<AppearanceProvider>(builder: (context, appearance, _) {
        final brightness = resolveAppearanceBrightness(appearance.mode, Brightness.dark);
        OmiColors.active = OmiColors.forBrightness(brightness);
        return MaterialApp(
          navigatorKey: navigatorKey,
          theme: buildOmiTheme(brightness: Brightness.light),
          darkTheme: buildOmiTheme(brightness: Brightness.dark),
          themeMode: appearance.mode,
          builder: (context, child) => KeyedSubtree(key: ValueKey(brightness), child: child!),
          home: Scaffold(
              body: TextButton(
            onPressed: () => navigatorKey.currentState!.push(MaterialPageRoute<void>(
              builder: (_) => Scaffold(
                  body: Container(
                key: const Key('palette_probe'),
                color: OmiColors.surface1,
                child: const Text('Current conversation'),
              )),
            )),
            child: const Text('Open'),
          )),
        );
      }),
    ));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    expect(find.text('Current conversation'), findsOneWidget);
    expect(tester.widget<Container>(find.byKey(const Key('palette_probe'))).color, OmiPalette.dark.surface1);
    await provider.setMode(ThemeMode.light);
    await tester.pumpAndSettle();
    expect(find.text('Current conversation'), findsOneWidget);
    expect(tester.widget<Container>(find.byKey(const Key('palette_probe'))).color, OmiPalette.light.surface1);
    OmiColors.active = OmiPalette.dark;
  });

  test('dark palette is identical to the original token values', () {
    const dark = OmiPalette.dark;
    expect([
      dark.surface0,
      dark.surface1,
      dark.surface2,
      dark.surface3,
      dark.border,
      dark.textPrimary,
      dark.textSecondary,
      dark.textTertiary,
      dark.textDisabled,
      dark.accent,
      dark.onAccent,
      dark.success,
      dark.successSurface,
      dark.warning,
      dark.danger,
      dark.dangerSurface,
    ], const [
      Color(0xFF000000),
      Color(0xFF1C1C1E),
      Color(0xFF2C2C2E),
      Color(0xFF3A3A3C),
      Color(0xFF3C3C43),
      Color(0xFFFFFFFF),
      Color(0xFFAEAEB2),
      Color(0xFF8E8E93),
      Color(0xFF636366),
      Color(0xFFFFFFFF),
      Color(0xFF000000),
      Color(0xFF30D158),
      Color(0x2630D158),
      Color(0xFFFF9F0A),
      Color(0xFFFF453A),
      Color(0x26FF453A),
    ]);
  });

  test('light controls contrast their parent surfaces while dark fills stay unchanged', () {
    expect(OmiPalette.dark.chipSurface, const Color(0xFF2C2C2E));
    expect(OmiPalette.dark.messageSurface, const Color(0xFF1C1C1E));
    expect(OmiPalette.dark.categorySurface, const Color(0xFF35343B));
    expect(OmiPalette.dark.conversationCard, const Color(0xFF1F1F25));
    expect(OmiPalette.dark.sourceBadgeSurface, const Color(0xFF2A2A31));
    expect(OmiPalette.light.chipSurface, isNot(OmiPalette.light.surface0));
    expect(OmiPalette.light.messageSurface, isNot(OmiPalette.light.surface1));
    expect(OmiPalette.light.categorySurface, isNot(OmiPalette.light.surface1));
    expect(OmiPalette.light.sourceBadgeSurface, isNot(OmiPalette.light.conversationCard));

    final conversation = ServerConversation(
      id: 'local',
      createdAt: DateTime(2026, 9, 27),
      structured: Structured('Planning', '', emoji: '*'),
    );
    OmiColors.active = OmiPalette.light;
    expect(conversation.getTagColor(), OmiPalette.light.categorySurface);
    expect(conversation.getTagTextColor(), OmiPalette.light.textPrimary);
    OmiColors.active = OmiPalette.dark;
    expect(conversation.getTagColor(), OmiPalette.dark.categorySurface);
    expect(conversation.getTagTextColor(), OmiPalette.dark.textPrimary);
  });
}
