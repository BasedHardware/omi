import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/conversations/date_query.dart';

final _now = DateTime(2026, 9, 30, 15, 30);

ConversationDateQuery _parse(String input) => parseConversationDateQuery(input, now: _now);

void _expectDay(ConversationDateQuery result, int year, int month, int day) {
  expect(result.startDate, DateTime(year, month, day));
  expect(result.endDate, DateTime(year, month, day + 1).subtract(const Duration(microseconds: 1)));
}

void main() {
  test('returns the normalized query untouched when no phrase matches', () {
    final result = _parse('  bluetooth   speaker  ');
    expect(result.query, 'bluetooth speaker');
    expect(result.hasDateFilter, isFalse);
    expect(result.matchedPhrase, isNull);
  });

  test('strips the matched phrase and keeps the remaining text', () {
    final result = _parse('bluetooth sept 12 call');
    expect(result.query, 'bluetooth call');
    _expectDay(result, 2026, 9, 12);
    expect(result.matchedPhrase, 'sept 12');
  });

  test('today and yesterday resolve to calendar days', () {
    _expectDay(_parse('today'), 2026, 9, 30);
    _expectDay(_parse('met sarah yesterday'), 2026, 9, 29);
  });

  test('bare weekdays pick the most recent including today', () {
    _expectDay(_parse('monday'), 2026, 9, 28);
    _expectDay(_parse('wednesday'), 2026, 9, 30);
    _expectDay(_parse('sunday'), 2026, 9, 27);
  });

  test('last weekday is strictly before today', () {
    _expectDay(_parse('last wednesday'), 2026, 9, 23);
    _expectDay(_parse('last tuesday'), 2026, 9, 29);
  });

  test('n days ago uses calendar arithmetic across a month boundary', () {
    _expectDay(_parse('5 days ago'), 2026, 9, 25);
    _expectDay(_parse('31 days ago'), 2026, 8, 30);
  });

  test('last week means the preceding Monday through Sunday', () {
    final result = _parse('last week');
    expect(result.startDate, DateTime(2026, 9, 21));
    expect(result.endDate, DateTime(2026, 9, 28).subtract(const Duration(microseconds: 1)));
  });

  test('last week stays midnight-aligned across DST transitions', () {
    for (final now in [DateTime(2026, 3, 9, 12), DateTime(2026, 11, 2, 12)]) {
      final result = parseConversationDateQuery('last week', now: now);
      final expectedMonday = DateTime(now.year, now.month, now.day - 7);
      expect(result.startDate, expectedMonday);
      expect(result.startDate!.hour, 0);
      expect(result.endDate, DateTime(now.year, now.month, now.day).subtract(const Duration(microseconds: 1)));
    }
  });

  test('a singular day offset parses like the plural form', () {
    _expectDay(_parse('1 day ago'), 2026, 9, 29);
  });

  test('year zero stays plain text', () {
    for (final phrase in ['sept 12 0000', '9/12/0000', 'sept 0000']) {
      final result = _parse(phrase);
      expect(result.hasDateFilter, isFalse, reason: phrase);
      expect(result.query, phrase);
    }
  });

  test('month names and abbreviations produce month ranges', () {
    final sept = _parse('september');
    expect(sept.startDate, DateTime(2026, 9, 1));
    expect(sept.endDate, DateTime(2026, 10, 1).subtract(const Duration(microseconds: 1)));

    final dec = _parse('dec');
    expect(dec.startDate, DateTime(2026, 12, 1));
    expect(dec.endDate, DateTime(2027, 1, 1).subtract(const Duration(microseconds: 1)));

    final withYear = _parse('sept 2025');
    expect(withYear.startDate, DateTime(2025, 9, 1));
    expect(withYear.endDate, DateTime(2025, 10, 1).subtract(const Duration(microseconds: 1)));
  });

  test('month plus day forms parse in either order', () {
    _expectDay(_parse('september 12'), 2026, 9, 12);
    _expectDay(_parse('sept12'), 2026, 9, 12);
    _expectDay(_parse('12 september'), 2026, 9, 12);
    _expectDay(_parse('sept 12 2025'), 2025, 9, 12);
    _expectDay(_parse('12 sept 2025'), 2025, 9, 12);
  });

  test('numeric US month/day parses with and without a year', () {
    _expectDay(_parse('9/12'), 2026, 9, 12);
    _expectDay(_parse('9/12/2025'), 2025, 9, 12);
  });

  test('a yearless date uses the current year rather than rolling back', () {
    _expectDay(_parse('october 3'), 2026, 10, 3);
    _expectDay(_parse('january 5'), 2026, 1, 5);
  });

  test('leap day validates strictly against the resolved year', () {
    _expectDay(_parse('feb 29 2024'), 2024, 2, 29);
    final invalid = _parse('feb 29');
    expect(invalid.hasDateFilter, isFalse);
    expect(invalid.query, 'feb 29');
  });

  test('invalid date-looking phrases stay plain text without partial matches', () {
    for (final phrase in ['sept 32', 'feb 30', '9/31', '2/30', '13/1']) {
      final result = _parse(phrase);
      expect(result.hasDateFilter, isFalse, reason: phrase);
      expect(result.query, phrase);
    }
    final embedded = _parse('call on sept 32');
    expect(embedded.hasDateFilter, isFalse);
  });

  test('word boundaries prevent partial name matches', () {
    for (final phrase in ['marching band', 'fri night', 'mondayish plans', 'todayish']) {
      expect(_parse(phrase).hasDateFilter, isFalse, reason: phrase);
    }
  });

  test('oversized day offsets are rejected', () {
    final result = _parse('40000 days ago');
    expect(result.hasDateFilter, isFalse);
  });

  test('on/in qualifiers strip only when they directly qualify the date', () {
    expect(_parse('call john on sept 12').query, 'call john');
    expect(_parse('meetings in march').query, 'meetings');
    expect(_parse('call on my friend sept 12').query, 'call on my friend');
  });

  test('the more specific phrase wins over a shorter month-only match', () {
    final result = _parse('sept 12');
    _expectDay(result, 2026, 9, 12);
    expect(result.query, '');
  });

  test('case is ignored', () {
    _expectDay(_parse('SEPT 12'), 2026, 9, 12);
    _expectDay(_parse('Last Monday'), 2026, 9, 28);
  });
}
