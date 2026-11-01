import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/paywall_reask.dart';

// The re-ask comes back 2, 3, 5 and then every 7 days after the last paywall, never on the
// first Home visit, and counts both arms at the same moments.

void main() {
  final day0 = DateTime(2026, 10, 14, 9);
  DateTime day(int n, [int hour = 9]) => DateTime(day0.year, day0.month, day0.day + n, hour);

  late List<String> exposures;
  late String? variant;

  Future<bool> check(DateTime now) => PaywallReask.checkDue(
        now: now,
        readVariant: (_) async => variant,
        recordExposure: (key, value) {
          exposures.add('$key=$value');
          return true;
        },
      );

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'reader-1'});
    await SharedPreferencesUtil.init();
    exposures = [];
    variant = 'test';
  });

  test('the gaps widen and then hold at a week', () {
    expect([for (var i = 0; i < 7; i++) PaywallReask.gapAfter(i)], [2, 3, 5, 7, 7, 7, 7]);
  });

  test('calendar days, not hours: a late open and an early open two days later count as 2', () {
    expect(PaywallReask.daysBetween(DateTime(2026, 10, 14, 23), DateTime(2026, 10, 16, 1)), 2);
    expect(PaywallReask.daysBetween(DateTime(2026, 10, 14, 1), DateTime(2026, 10, 14, 23)), 0);
  });

  test('never on the first Home visit; due two days later; then the schedule widens', () async {
    expect(await check(day0), isFalse, reason: 'first visit starts the clock');
    expect(exposures, isEmpty);
    expect(await check(day(1)), isFalse);
    expect(await check(day(2)), isTrue, reason: 'gap 2 after the first visit');
    expect(await check(day(2, 18)), isFalse, reason: 'at most once a day');
    expect(await check(day(4)), isFalse);
    expect(await check(day(5)), isTrue, reason: 'second gap is 3');
    expect(await check(day(9)), isFalse);
    expect(await check(day(10)), isTrue, reason: 'third gap is 5');
    expect(await check(day(16)), isFalse);
    expect(await check(day(17)), isTrue, reason: 'then weekly');
    expect(await check(day(24)), isTrue, reason: 'still weekly');
    expect(exposures, everyElement('paywall-reask=test'));
    expect(exposures, hasLength(5));
  });

  test('any other paywall restarts the clock', () async {
    await check(day0);
    PaywallReask.noteShown(now: day(1)); // e.g. a locked conversation
    expect(await check(day(2)), isFalse);
    expect(await check(day(3)), isTrue);
  });

  test('control is exposed on the same schedule but shows nothing', () async {
    variant = 'control';
    await check(day0);
    expect(await check(day(2)), isFalse);
    expect(exposures, ['paywall-reask=control']);
    expect(await check(day(4)), isFalse);
    expect(await check(day(5)), isFalse);
    expect(exposures, hasLength(2), reason: 'control advances the same schedule');
  });

  test('an unread flag shows nothing, exposes no one and keeps the reader due', () async {
    variant = null;
    await check(day0);
    expect(await check(day(2)), isFalse);
    expect(exposures, isEmpty);
    variant = 'test';
    expect(await check(day(3)), isTrue, reason: 'still due once the flag is read');
  });

  test('no signed-in reader: nothing happens', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    expect(await check(day(30)), isFalse);
    expect(exposures, isEmpty);
  });
}
