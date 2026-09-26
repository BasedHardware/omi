import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/appearance_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/appearance_preferences.dart';

/// Light mode: every token follows the active palette, the app root switches it for Settings →
/// Appearance and for the phone's own setting, and the whole tree repaints without losing state.

class _Probe extends StatelessWidget {
  const _Probe();

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      key: const Key('probe'),
      color: OmiColors.surface0,
      child: Text('probe', style: OmiType.body, textDirection: TextDirection.ltr),
    );
  }
}

class _Counter extends StatefulWidget {
  const _Counter();

  @override
  State<_Counter> createState() => _CounterState();
}

class _CounterState extends State<_Counter> {
  int taps = 0;

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: () => setState(() => taps++),
        child: Text('taps $taps', textDirection: TextDirection.ltr, style: TextStyle(color: OmiColors.textPrimary)),
      );
}

Color _probeColor(WidgetTester tester) => tester.widget<ColoredBox>(find.byKey(const Key('probe'))).color;

void main() {
  tearDown(() {
    OmiAppearance.mode.value = OmiAppearanceMode.system;
    OmiColors.use(OmiPalette.dark);
    OmiHaptics.enabled = true;
  });

  test('a mode resolves to its palette; System follows the phone', () {
    expect(OmiAppearance.resolve(OmiAppearanceMode.light, Brightness.dark), same(OmiPalette.light));
    expect(OmiAppearance.resolve(OmiAppearanceMode.dark, Brightness.light), same(OmiPalette.dark));
    expect(OmiAppearance.resolve(OmiAppearanceMode.system, Brightness.light), same(OmiPalette.light));
    expect(OmiAppearance.resolve(OmiAppearanceMode.system, Brightness.dark), same(OmiPalette.dark));
  });

  test('switching the palette switches every colour and text style token', () {
    OmiColors.use(OmiPalette.light);
    expect(OmiColors.isLight, isTrue);
    expect(OmiColors.surface0, OmiPalette.light.surface0);
    expect(OmiColors.textPrimary, OmiPalette.light.textPrimary);
    expect(OmiType.body.color, OmiPalette.light.textPrimary);
    expect(OmiType.largeTitle.color, OmiPalette.light.textPrimary);
    // The light page is pale and its text dark; the accent follows the text.
    expect(OmiColors.surface0.computeLuminance(), greaterThan(0.8));
    expect(OmiColors.textPrimary.computeLuminance(), lessThan(0.05));
    expect(OmiColors.accent, OmiColors.textPrimary);

    OmiColors.use(OmiPalette.dark);
    expect(OmiColors.isLight, isFalse);
    expect(OmiType.body.color, OmiPalette.dark.textPrimary);
  });

  test('the light palette keeps text readable (WCAG AA) on its surfaces', () {
    double contrast(Color a, Color b) {
      final la = a.computeLuminance(), lb = b.computeLuminance();
      return (la > lb ? la + 0.05 : lb + 0.05) / (la > lb ? lb + 0.05 : la + 0.05);
    }

    const p = OmiPalette.light;
    for (final surface in [p.surface0, p.surface1]) {
      expect(contrast(p.textPrimary, surface), greaterThan(7));
      expect(contrast(p.textSecondary, surface), greaterThan(4.5));
      expect(contrast(p.danger, surface), greaterThan(4.4));
    }
    expect(contrast(p.textTertiary, p.surface1), greaterThan(4.5));
    expect(contrast(p.onAccent, p.accent), greaterThan(7));
  });

  testWidgets('choosing a mode repaints the whole tree, const widgets included, and keeps state', (tester) async {
    OmiAppearance.mode.value = OmiAppearanceMode.dark;
    await tester.pumpWidget(
      OmiAppearanceScope(builder: (_) => const Column(children: [_Probe(), _Counter()])),
    );
    expect(_probeColor(tester), OmiPalette.dark.surface0);
    await tester.tap(find.text('taps 0'));
    await tester.pump();
    expect(find.text('taps 1'), findsOneWidget);

    OmiAppearance.mode.value = OmiAppearanceMode.light;
    await tester.pump();
    expect(_probeColor(tester), OmiPalette.light.surface0);
    expect(tester.widget<Text>(find.text('probe')).style?.color, OmiPalette.light.textPrimary);
    // Same State object: the count survived the switch.
    expect(find.text('taps 1'), findsOneWidget);
    expect(tester.widget<Text>(find.text('taps 1')).style?.color, OmiPalette.light.textPrimary);

    OmiAppearance.mode.value = OmiAppearanceMode.dark;
    await tester.pump();
    expect(_probeColor(tester), OmiPalette.dark.surface0);
  });

  testWidgets('a sheet left open under a theme switch repaints itself, not just its content', (tester) async {
    // Settings → Appearance: the sheet stays open under the page where the switch happens, and must
    // not come back dark behind light cards (or the other way round).
    OmiAppearance.mode.value = OmiAppearanceMode.dark;
    await tester.pumpWidget(OmiAppearanceScope(
      builder: (_) => MaterialApp(
        theme: buildOmiTheme(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => showOmiSheet<void>(context: context, builder: (_) => const _Probe()),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    Color sheetColor() => tester
        .widget<Material>(find.descendant(of: find.byType(BottomSheet), matching: find.byType(Material)).first)
        .color!;
    expect(sheetColor(), OmiPalette.dark.sheet);

    OmiAppearance.mode.value = OmiAppearanceMode.light;
    await tester.pumpAndSettle();
    expect(sheetColor(), OmiPalette.light.sheet);
    expect(_probeColor(tester), OmiPalette.light.surface0);

    OmiAppearance.mode.value = OmiAppearanceMode.dark;
    await tester.pumpAndSettle();
    expect(sheetColor(), OmiPalette.dark.sheet);
  });

  testWidgets('System follows the phone when it switches between light and dark', (tester) async {
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    OmiAppearance.mode.value = OmiAppearanceMode.system;
    await tester.pumpWidget(OmiAppearanceScope(builder: (_) => const _Probe()));
    expect(_probeColor(tester), OmiPalette.light.surface0);

    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    await tester.pump();
    expect(_probeColor(tester), OmiPalette.dark.surface0);
  });

  testWidgets('Settings → Appearance picks a mode, remembers it, and turns haptics off', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    restoreAppearance();
    expect(OmiAppearance.mode.value, OmiAppearanceMode.system);

    await tester.pumpWidget(
      OmiAppearanceScope(
        builder: (_) => MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          locale: const Locale('en'),
          home: const AppearancePage(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final en = lookupAppLocalizations(const Locale('en'));
    expect(find.text(en.appearanceSystem), findsOneWidget);
    expect(find.text(en.appearanceLight), findsOneWidget);
    expect(find.text(en.appearanceDark), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('appearance_light')));
    await tester.pumpAndSettle();
    expect(OmiAppearance.mode.value, OmiAppearanceMode.light);
    expect(OmiColors.isLight, isTrue);
    expect(SharedPreferencesUtil().appearanceMode, 'light');
    expect(tester.getSemantics(find.byKey(const ValueKey('appearance_light'))), isSemantics(isSelected: true));
    expect(tester.getSemantics(find.byKey(const ValueKey('appearance_system'))), isSemantics(isSelected: false));

    await tester.tap(find.byKey(const ValueKey('appearance_dark')));
    await tester.pumpAndSettle();
    expect(OmiColors.isLight, isFalse);
    expect(SharedPreferencesUtil().appearanceMode, 'dark');

    expect(OmiHaptics.enabled, isTrue);
    await tester.tap(find.byKey(const ValueKey('appearance_haptics')));
    await tester.pumpAndSettle();
    expect(OmiHaptics.enabled, isFalse);
    expect(SharedPreferencesUtil().hapticsEnabled, isFalse);

    // A new launch restores both from what was saved.
    SharedPreferencesUtil().appearanceMode = 'light';
    OmiHaptics.enabled = true;
    restoreAppearance();
    expect(OmiAppearance.mode.value, OmiAppearanceMode.light);
    expect(OmiHaptics.enabled, isFalse);
  });
}
