import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Regression guard for the free-tier listening-minute copy.
///
/// Prod entitlement is `BASIC_TIER_MINUTES_LIMIT_PER_MONTH = 300`
/// (see backend env / `get_plan_features`). User-facing l10n strings that
/// state the free/premium monthly minute allowance must say **300**, never the
/// legacy 1200/600 figures. The backend env remains the source of truth; these
/// strings are the only hardcoded fallbacks and are kept in sync here.
void main() {
  const keys = [
    'freeMinutesMonth',
    'basicPlanDescription',
    'premiumMinutesInfo',
    'premiumMinutesMonth',
  ];

  // Known stale representations of the old 1200/600 allowance, across the
  // Latin / Bengali / Devanagari number scripts used by our locales.
  const staleForms = ['1200', '1.200', '1 200', '1,200', '১,২০০', '१,२००', '600'];

  final l10nDir = Directory('lib/l10n');

  Map<String, String> loadValues(File f) {
    final json = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
    return {
      for (final k in keys)
        if (json[k] is String) k: json[k] as String,
    };
  }

  test('English template states the 300 free/premium minute allowance', () {
    // English is the localization source-of-truth template.
    final en = loadValues(File('lib/l10n/app_en.arb'));
    for (final k in keys) {
      expect(en[k], contains('300'), reason: 'en.$k must state 300');
      expect(en[k], isNot(contains('1200')), reason: 'en.$k must not state 1200');
      expect(en[k], isNot(contains('600')), reason: 'en.$k must not state 600');
    }
  });

  test('no locale hardcodes a stale 1200/600 free-tier minute allowance', () {
    final arbFiles = l10nDir
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.arb'))
        .where((f) => RegExp(r'app_[a-z]+\.arb$').hasMatch(f.path))
        .toList();

    expect(arbFiles, isNotEmpty, reason: 'expected locale arb files under lib/l10n');

    final violations = <String>[];
    for (final f in arbFiles) {
      final locale = f.uri.pathSegments.last;
      for (final entry in loadValues(f).entries) {
        for (final form in staleForms) {
          if (entry.value.contains(form)) {
            violations.add('$locale.${entry.key} contains "$form"');
          }
        }
      }
    }

    expect(
      violations,
      isEmpty,
      reason: 'free/premium minute copy must not carry the legacy 1200/600 allowance:\n${violations.join('\n')}',
    );
  });
}
