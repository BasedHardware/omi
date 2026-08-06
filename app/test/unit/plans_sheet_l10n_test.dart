import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/plan_pricing.dart';

/// The plans sheet shipped hardcoded English while its ARB keys already existed
/// and were translated, so a Japanese user saw an English paywall. These cover
/// the two halves of the fix: the keys resolve per locale, and the months-free
/// badge is a count the caller localizes rather than a pre-built English label.

/// Every plans-sheet string the sheet now looks up. Kept explicit so a key that
/// gets dropped from a locale fails here rather than silently rendering English.
const _planSheetKeys = [
  'planSheetChooseYourPlan',
  'availableOnMacMobileWeb',
  'popularBadge',
  'worksOnDesktop',
  'noDesktopAccess',
  'annualBillingSummary',
  'monthsFreeBadge',
  'endsOnDate',
  'planEndedResubscribe',
  'planCancelsResubscribe',
  'freemiumLimitsIntro',
  'downgradeLimitDelayNotRealTime',
  'downgradeToFreemiumAction',
  'getFreeUnlimitedAccess',
  'shareDataForTraining',
  'yourRequestUnderReview',
  // Pre-existing keys the sheet was ignoring until this change.
  'unlimitedConversations',
  'askOmiAnything',
  'unlockOmiInfiniteMemory',
  'selectedPlanNotAvailable',
  'upgradeAlreadyScheduled',
  'annualPlanStartsAutomatically',
  'planRenewsOn',
  'youreOnAnnualPlan',
  'alreadyBestValuePlan',
];

Map<String, dynamic> _arb(String locale) =>
    jsonDecode(File('lib/l10n/app_$locale.arb').readAsStringSync()) as Map<String, dynamic>;

List<Map<String, dynamic>> _tier({required int monthly, required int yearly}) => [
      {'interval': 'month', 'unit_amount': monthly},
      {'interval': 'year', 'unit_amount': yearly},
    ];

void main() {
  group('every locale carries the plans-sheet copy', () {
    final locales = Directory('lib/l10n')
        .listSync()
        .whereType<File>()
        .map((f) => f.path.split('/').last)
        .where((n) => n.startsWith('app_') && n.endsWith('.arb'))
        .map((n) => n.substring(4, n.length - 4))
        .toList()
      ..sort();

    test('the template defines all of them', () {
      final en = _arb('en');
      expect(locales, contains('en'));
      for (final key in _planSheetKeys) {
        expect(en[key], isA<String>(), reason: '$key missing from the English template');
      }
    });

    for (final locale in locales) {
      test(locale, () {
        final values = _arb(locale);
        for (final key in _planSheetKeys) {
          expect(values[key], isA<String>(), reason: '$locale is missing $key');
          expect((values[key] as String).trim(), isNotEmpty, reason: '$locale has an empty $key');
        }
      });
    }
  });

  group('placeholders survive translation', () {
    test('date and price placeholders are present in every locale', () {
      final withDate = ['endsOnDate', 'planEndedResubscribe', 'planCancelsResubscribe', 'planRenewsOn'];
      for (final file in Directory('lib/l10n').listSync().whereType<File>()) {
        final name = file.path.split('/').last;
        if (!name.startsWith('app_') || !name.endsWith('.arb')) continue;
        final locale = name.substring(4, name.length - 4);
        final values = _arb(locale);
        for (final key in withDate) {
          expect(values[key], contains('{date}'), reason: '$locale.$key dropped the {date} placeholder');
        }
        expect(values['annualBillingSummary'], contains('{months}'), reason: '$locale dropped {months}');
        expect(values['annualBillingSummary'], contains('{price}'), reason: '$locale dropped {price}');
        expect(values['monthsFreeBadge'], contains('plural'), reason: '$locale.monthsFreeBadge is not a plural');
        expect(values['monthsFreeBadge'], contains('{count}'), reason: '$locale.monthsFreeBadge dropped {count}');
      }
    });
  });

  group('generated lookups resolve per locale', () {
    test('English and Japanese return their own copy', () async {
      final en = await AppLocalizations.delegate.load(const Locale('en'));
      final ja = await AppLocalizations.delegate.load(const Locale('ja'));

      expect(en.popularBadge, 'POPULAR');
      expect(ja.popularBadge, isNot('POPULAR'), reason: 'Japanese must not fall back to the English badge');
      expect(ja.availableOnMacMobileWeb, isNot(en.availableOnMacMobileWeb));
      expect(ja.noDesktopAccess, isNot(en.noDesktopAccess));
    });

    test('the months-free badge pluralizes', () async {
      final en = await AppLocalizations.delegate.load(const Locale('en'));
      expect(en.monthsFreeBadge(1), '1 Month Free');
      expect(en.monthsFreeBadge(3), '3 Months Free');
    });

    test('interpolated strings substitute their argument', () async {
      final en = await AppLocalizations.delegate.load(const Locale('en'));
      expect(en.endsOnDate('Aug 6, 2026'), contains('Aug 6, 2026'));
      expect(en.annualBillingSummary(12, '\$161.91'), '12 months / \$161.91');
      expect(en.planRenewsOn('Sep 1, 2026'), contains('Sep 1, 2026'));
    });
  });

  // The count itself is covered in test/utils/plan_pricing_test.dart; this is
  // the half that matters here — a count reaches the user as localized copy.
  test('the months-free count renders through the localized badge', () async {
    final months = annualMonthsFree(_tier(monthly: 1799, yearly: 16191));
    final ja = await AppLocalizations.delegate.load(const Locale('ja'));
    expect(months, 3);
    expect(ja.monthsFreeBadge(months!), isNot(contains('Months Free')));
  });
}
