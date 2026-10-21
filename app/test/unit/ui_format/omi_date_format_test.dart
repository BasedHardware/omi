import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_date_format.dart';
import 'package:omi/utils/other/temp.dart';

/// Dates follow the locale and the 24-hour setting instead of a hardcoded `h:mm a` en_US pattern.
void main() {
  setUpAll(() async {
    await initializeDateFormatting();
  });

  // Wednesday, 23 September 2026, 14:05 local.
  final now = DateTime(2026, 9, 23, 14, 5);

  OmiDateFormat fmt(Locale locale, {bool h24 = false}) =>
      OmiDateFormat(locale: locale, use24HourFormat: h24, l10n: lookupAppLocalizations(locale), clock: () => now);

  // intl separates the period with a narrow no-break space in modern CLDR; compare on plain spaces.
  String plain(String s) => s.replaceAll('\u202f', ' ').replaceAll('\u00a0', ' ');

  group('time', () {
    test('en_US 12h vs 24h setting', () {
      final t = DateTime(2026, 9, 23, 14, 5);
      expect(plain(fmt(const Locale('en', 'US')).time(t)), '2:05 PM');
      expect(fmt(const Locale('en', 'US'), h24: true).time(t), '14:05');
    });

    test('de and fr default to 24h even without the setting', () {
      final t = DateTime(2026, 9, 23, 14, 5);
      expect(fmt(const Locale('de')).time(t), '14:05');
      expect(fmt(const Locale('fr')).time(t), '14:05');
    });
  });

  group('dayHeader', () {
    test('today and yesterday are localized words', () {
      expect(fmt(const Locale('en')).dayHeader(DateTime(2026, 9, 23, 9)), 'Today');
      expect(fmt(const Locale('en')).dayHeader(DateTime(2026, 9, 22, 23, 59)), 'Yesterday');
      expect(
          fmt(const Locale('de')).dayHeader(DateTime(2026, 9, 23)), lookupAppLocalizations(const Locale('de')).today);
      expect(
        fmt(const Locale('fr')).dayHeader(DateTime(2026, 9, 22)),
        lookupAppLocalizations(const Locale('fr')).yesterday,
      );
    });

    test('weekday + month day this year, with the year otherwise, in the locale', () {
      expect(fmt(const Locale('en', 'US')).dayHeader(DateTime(2026, 9, 1)), 'Tue, Sep 1');
      expect(fmt(const Locale('en', 'US')).dayHeader(DateTime(2025, 12, 3)), 'Wed, Dec 3, 2025');
      final de = fmt(const Locale('de')).dayHeader(DateTime(2026, 9, 1));
      expect(de, contains('Sept'));
      expect(de, startsWith('Di'));
      final fr = fmt(const Locale('fr')).dayHeader(DateTime(2025, 12, 3));
      expect(fr, contains('déc'));
      expect(fr, contains('2025'));
    });
  });

  test('date and dateTime follow locale order', () {
    final t = DateTime(2026, 9, 23, 14, 5);
    expect(fmt(const Locale('en', 'US')).date(t), 'Sep 23, 2026');
    expect(fmt(const Locale('de')).date(t), '23. Sept. 2026');
    expect(plain(fmt(const Locale('en', 'US')).dateTime(t)), 'Sep 23, 2026 2:05 PM');
    expect(fmt(const Locale('en', 'US'), h24: true).dateTime(t), contains('14:05'));
    expect(fmt(const Locale('fr')).dateTime(t), allOf(contains('23 sept. 2026'), contains('14:05')));
  });

  group('timeRange', () {
    test('same day, same period: the period is written once', () {
      final range =
          fmt(const Locale('en', 'US')).timeRange(DateTime(2026, 9, 23, 10, 17), DateTime(2026, 9, 23, 11, 19));
      expect(plain(range), '10:17 – 11:19 AM');
    });

    test('same day across noon keeps both periods', () {
      final range =
          fmt(const Locale('en', 'US')).timeRange(DateTime(2026, 9, 23, 11, 50), DateTime(2026, 9, 23, 12, 10));
      expect(plain(range), '11:50 AM – 12:10 PM');
    });

    test('24h', () {
      expect(
        fmt(const Locale('en', 'US'), h24: true)
            .timeRange(DateTime(2026, 9, 23, 10, 17), DateTime(2026, 9, 23, 11, 19)),
        '10:17 – 11:19',
      );
      expect(
        fmt(const Locale('de')).timeRange(DateTime(2026, 9, 23, 10, 17), DateTime(2026, 9, 23, 11, 19)),
        '10:17 – 11:19',
      );
    });

    test('cross-day shows both dates', () {
      final range =
          fmt(const Locale('en', 'US')).timeRange(DateTime(2026, 9, 22, 23, 30), DateTime(2026, 9, 23, 0, 45));
      expect(plain(range), 'Sep 22, 2026 11:30 PM – Sep 23, 2026 12:45 AM');
    });
  });

  test('timestamp: time today, "Yesterday at" yesterday, date + time before', () {
    final en = fmt(const Locale('en', 'US'));
    expect(plain(en.timestamp(DateTime(2026, 9, 23, 9, 3))), '9:03 AM');
    expect(plain(en.timestamp(DateTime(2026, 9, 22, 9, 3))), 'Yesterday at 9:03 AM');
    expect(plain(en.timestamp(DateTime(2026, 9, 1, 9, 3))), 'Sep 1 9:03 AM');
    expect(fmt(const Locale('de')).timestamp(DateTime(2026, 9, 1, 9, 3)), contains('09:03'));
  });

  test('a locale intl lacks falls back instead of throwing', () {
    expect(OmiDateFormat.resolveIntlLocale(const Locale('xx')), 'en');
    expect(OmiDateFormat.resolveIntlLocale(const Locale('pt', 'BR')), 'pt_BR');
    expect(OmiDateFormat.resolveIntlLocale(const Locale('de', 'ZZ')), 'de');
  });

  testWidgets('of(context) reads the locale and the device 24-hour setting', (tester) async {
    late OmiDateFormat captured;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('en', 'US'),
        delegates: const [AppLocalizations.delegate, DefaultWidgetsLocalizations.delegate],
        child: MediaQuery(
          data: const MediaQueryData(alwaysUse24HourFormat: true),
          child: Builder(builder: (context) {
            captured = OmiDateFormat.of(context);
            return const SizedBox();
          }),
        ),
      ),
    );
    await tester.pump();
    expect(captured.use24HourFormat, isTrue);
    expect(captured.time(DateTime(2026, 1, 1, 18, 30)), '18:30');
  });

  test('formatChatTimestamp delegates without a context', () {
    final today = DateTime.now();
    final value = DateTime(today.year, today.month, today.day, 9, 3);
    expect(plain(formatChatTimestamp(value)), '9:03 AM');
  });
}
