import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

import 'package:omi/ui/ui.dart';

import 'ui_test_app.dart';

double _contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

void main() {
  test('the theme draws unstyled spinners and accents visibly on the page', () {
    final theme = buildOmiTheme();
    final page = theme.scaffoldBackgroundColor;
    expect(page, OmiColors.surface0);
    expect(theme.useMaterial3, isFalse);

    // CircularProgressIndicator resolves its colour as theme.progressIndicatorTheme.color, then
    // colorScheme.primary. Both used to be black on the black page.
    final spinner = theme.progressIndicatorTheme.color ?? theme.colorScheme.primary;
    expect(_contrast(spinner, page), greaterThan(7));
    expect(_contrast(theme.colorScheme.primary, page), greaterThan(7));
    expect(_contrast(theme.colorScheme.onPrimary, theme.colorScheme.primary), greaterThan(7));
    expect(theme.appBarTheme.centerTitle, isTrue);
    expect(theme.appBarTheme.backgroundColor, OmiColors.surface0);
    expect(theme.snackBarTheme.behavior, SnackBarBehavior.floating);
  });

  test('token contrast meets WCAG AA on cards', () {
    for (final surface in [OmiColors.surface0, OmiColors.surface1]) {
      expect(_contrast(OmiColors.textTertiary, surface), greaterThanOrEqualTo(4.5));
      expect(_contrast(OmiColors.textSecondary, surface), greaterThanOrEqualTo(4.5));
      expect(_contrast(OmiColors.danger, surface), greaterThanOrEqualTo(4.5));
    }
  });

  testWidgets('an unstyled CircularProgressIndicator paints white under the app theme', (tester) async {
    await pumpUi(tester, const Scaffold(body: Center(child: CircularProgressIndicator())));
    final context = tester.element(find.byType(CircularProgressIndicator));
    final resolved = ProgressIndicatorTheme.of(context).color ?? Theme.of(context).colorScheme.primary;
    expect(resolved, OmiColors.accent);
  });

  testWidgets('OmiMotion returns zero durations when the system asks to remove animations', (tester) async {
    late OmiMotion reduced;
    late OmiMotion full;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(disableAnimations: true),
        child: Builder(builder: (context) {
          reduced = OmiMotion.of(context);
          return const SizedBox();
        }),
      ),
    );
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(),
        child: Builder(builder: (context) {
          full = OmiMotion.of(context);
          return const SizedBox();
        }),
      ),
    );
    expect(reduced.quick, Duration.zero);
    expect(reduced.standard, Duration.zero);
    expect(reduced.emphasized, Duration.zero);
    expect(full.quick, OmiMotion.quickDuration);
    expect(full.standard, const Duration(milliseconds: 250));
    expect(full.emphasized, const Duration(milliseconds: 400));
  });

  test('syncIntlDefaultLocale follows the app locale and ignores locales without date data', () async {
    final previous = Intl.defaultLocale;
    addTearDown(() => Intl.defaultLocale = previous);
    await initializeDateFormatting('de');

    syncIntlDefaultLocale(const Locale('de'));
    expect(Intl.defaultLocale, 'de');
    expect(DateFormat.MMMM().format(DateTime(2026, 3, 1)), 'März');

    syncIntlDefaultLocale(const Locale('xx'));
    expect(Intl.defaultLocale, 'de', reason: 'an unknown locale must not replace a working one');
  });
}
