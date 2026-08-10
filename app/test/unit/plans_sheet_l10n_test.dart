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
  'freemiumLimitsIntro',
  'downgradeLimitDelayNotRealTime',
  'downgradeToFreemiumAction',
  'getFreeUnlimitedAccess',
  'shareDataForTraining',
  'yourRequestUnderReview',
  // Pre-existing keys the sheet was ignoring until this change. Reusing these
  // is the point: a second key with the same meaning is the defect that
  // `no plans-sheet key repeats another key's text` below now catches.
  'unlimitedConversations',
  'askOmiAnything',
  'unlockOmiInfiniteMemory',
  'selectedPlanNotAvailable',
  'upgradeScheduled',
  'upgradeAlreadyScheduled',
  'annualPlanStartsAutomatically',
  'planRenewsOn',
  'planEndedOn',
  'planSetToCancelOn',
  'endsOnDate',
  'youreOnAnnualPlan',
  'alreadyBestValuePlan',
  'trainingDataProgram',
];

Map<String, dynamic> _arb(String locale) =>
    jsonDecode(File('lib/l10n/app_$locale.arb').readAsStringSync()) as Map<String, dynamic>;

/// Top-level keys as they literally appear in the file, duplicates included.
///
/// `jsonDecode` silently keeps the last of a repeated key, so a second
/// definition of an existing key is invisible to every other check here — it
/// just quietly replaces a translated string across all 49 locales.
List<String> _rawKeys(File arb) =>
    RegExp(r'^    "([^"]+)":', multiLine: true).allMatches(arb.readAsStringSync()).map((m) => m.group(1)!).toList();

List<Map<String, dynamic>> _tier({required int monthly, required int yearly}) => [
  {'interval': 'month', 'unit_amount': monthly},
  {'interval': 'year', 'unit_amount': yearly},
];

void main() {
  group('every locale carries the plans-sheet copy', () {
    final locales =
        Directory('lib/l10n')
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

  test('no ARB defines the same key twice', () {
    // Regression: this PR first shipped a second `endsOnDate` alongside the one
    // that already existed, in all 49 files. Nothing failed — jsonDecode kept
    // the new value, the old translation went dead, and the only reason it was
    // caught was review.
    for (final arb in Directory('lib/l10n').listSync().whereType<File>()) {
      final name = arb.path.split('/').last;
      if (!name.startsWith('app_') || !name.endsWith('.arb')) continue;
      final keys = _rawKeys(arb);
      final duplicates = keys.where((k) => keys.where((o) => o == k).length > 1).toSet();
      expect(duplicates, isEmpty, reason: '$name defines these keys more than once: $duplicates');
    }
  });

  test("no plans-sheet key repeats another key's text", () {
    // Regression: planEndedResubscribe and planCancelsResubscribe shipped with
    // text identical to the existing planEndedOn / planSetToCancelOn, and
    // endsOnDate was added on top of a key of the same name. A second key
    // saying the same thing splits future translation work in two and lets the
    // two copies drift. The duplicate-key check above cannot see this one,
    // because the names differ.
    final en = _arb('en');
    final byValue = <String, List<String>>{};
    en.forEach((key, value) {
      if (key.startsWith('@') || value is! String) return;
      byValue.putIfAbsent(value, () => []).add(key);
    });
    for (final key in _planSheetKeys) {
      final twins = byValue[en[key] as String]!.where((k) => k != key).toList();
      expect(twins, isEmpty, reason: '$key says the same thing as $twins — reuse one of them instead');
    }
  });

  group('placeholders survive translation', () {
    test('date and price placeholders are present in every locale', () {
      final withDate = ['endsOnDate', 'planEndedOn', 'planSetToCancelOn', 'planRenewsOn'];
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

    test('languages with few/many use the right noun form past 4', () async {
      // =1/other alone renders the 2-4 form for every larger count. The badge
      // is derived from live Stripe prices, so 5+ is reachable if a tier's
      // annual discount deepens.
      final ru = await AppLocalizations.delegate.load(const Locale('ru'));
      expect(ru.monthsFreeBadge(1), contains('месяц '));
      expect(ru.monthsFreeBadge(3), contains('месяца'));
      expect(ru.monthsFreeBadge(7), contains('месяцев'));

      final pl = await AppLocalizations.delegate.load(const Locale('pl'));
      expect(pl.monthsFreeBadge(3), contains('miesiące'));
      expect(pl.monthsFreeBadge(7), contains('miesięcy'));

      final hr = await AppLocalizations.delegate.load(const Locale('hr'));
      expect(hr.monthsFreeBadge(3), contains('mjeseca'));
      expect(hr.monthsFreeBadge(7), contains('mjeseci'));
    });

    test('interpolated strings substitute their argument', () async {
      final en = await AppLocalizations.delegate.load(const Locale('en'));
      // Reuses the pre-existing endsOnDate rather than declaring a second one.
      expect(en.endsOnDate('Aug 6, 2026'), 'Ends Aug 6, 2026');
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
