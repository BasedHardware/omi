import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/omi_duration.dart';
import 'package:omi/utils/other/time_utils.dart';

/// One duration vocabulary: offsets never drop the hour, and list/detail lengths come from one
/// formatter.
void main() {
  group('offset', () {
    test('m:ss under an hour', () {
      expect(OmiDuration.offset(0), '0:00');
      expect(OmiDuration.offset(5), '0:05');
      expect(OmiDuration.offset(218), '3:38');
      expect(OmiDuration.offset(3599), '59:59');
    });

    test('h:mm:ss from an hour — the hour is never dropped', () {
      expect(OmiDuration.offset(3600), '1:00:00');
      expect(OmiDuration.offset(3900), '1:05:00', reason: 'was rendered "5:00" by the playback bar');
      expect(OmiDuration.offset(3725), '1:02:05');
      expect(OmiDuration.offset(36000 + 61), '10:01:01');
    });

    test('fractions floor, negatives and NaN clamp to zero', () {
      expect(OmiDuration.offset(5.9), '0:05');
      expect(OmiDuration.offset(-3), '0:00');
      expect(OmiDuration.offset(double.nan), '0:00');
    });

    test('secondsToHMS delegates', () => expect(secondsToHMS(3725), '1:02:05'));
  });

  group('compact', () {
    test('English fallback', () {
      expect(OmiDuration.compact(8), '8s');
      expect(OmiDuration.compact(250), '4m 10s');
      expect(OmiDuration.compact(2530), '42m');
      expect(OmiDuration.compact(3900), '1h 5m');
      expect(OmiDuration.compact(3600 * 12 + 60), '12h');
      expect(OmiDuration.compact(-1), '0s');
    });

    test('localized units', () {
      final de = lookupAppLocalizations(const Locale('de'));
      expect(OmiDuration.compact(3900, de), de.timeCompactHoursAndMins(1, 5));
      expect(OmiDuration.compact(8, de), de.timeCompactSecs(8));
    });
  });

  group('long', () {
    test('English fallback and localized', () {
      expect(OmiDuration.long(1), '1 secs');
      expect(OmiDuration.long(754), '12 mins 34 secs');
      expect(OmiDuration.long(3900), '1 hours 5 mins');
      expect(OmiDuration.long(86400 * 2 + 3600 * 3), '2 days 3 hours');
      final en = lookupAppLocalizations(const Locale('en'));
      expect(OmiDuration.long(754, en), en.timeMinsAndSecs(12, 34));
      expect(OmiDuration.long(60, en), en.timeMinSingular(1));
    });
  });

  testWidgets('legacy helpers agree with OmiDuration', (tester) async {
    late BuildContext context;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('fr'),
        delegates: const [AppLocalizations.delegate, DefaultWidgetsLocalizations.delegate],
        child: Builder(builder: (c) {
          context = c;
          return const SizedBox();
        }),
      ),
    );
    await tester.pump();
    final fr = lookupAppLocalizations(const Locale('fr'));
    expect(secondsToCompactDuration(3900, context), OmiDuration.compact(3900, fr));
    expect(secondsToHumanReadable(754, context), OmiDuration.long(754, fr));
  });
}
