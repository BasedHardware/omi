import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/battery_display_policy.dart';

void main() {
  late DateTime now;
  late BatteryDisplayPolicy policy;

  setUp(() {
    now = DateTime.utc(2026, 11, 27, 12);
    policy = BatteryDisplayPolicy(clock: () => now)..beginConnection('omi');
  });

  void advance(Duration d) => now = now.add(d);

  test('a low reading while charging is hidden; a high one shows', () {
    policy.onCharging('omi', true);
    policy.onSample(1, charging: true);
    expect(policy.hideReason(1, charging: true), BatteryHideReason.chargingLow);
    expect(policy.hideReason(19, charging: true), BatteryHideReason.chargingLow);
    expect(policy.hideReason(20, charging: true), isNull);
  });

  test('an ordinary near-empty reading shows until it has stayed flat', () {
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), isNull);
    expect(policy.untilFlat(1, charging: false), BatteryDisplayPolicy.flatHold);
    advance(const Duration(minutes: 9));
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), isNull);
    advance(const Duration(minutes: 1));
    expect(policy.hideReason(1, charging: false), BatteryHideReason.flat);
    expect(policy.untilFlat(1, charging: false), isNull);
  });

  test('a falling near-empty reading is real and always shows', () {
    policy.markFirstPairing('omi');
    policy.onSample(3, charging: false);
    expect(policy.hideReason(3, charging: false), BatteryHideReason.firstPairing);
    policy.onSample(2, charging: false);
    expect(policy.hideReason(2, charging: false), isNull);
    advance(const Duration(minutes: 30));
    expect(policy.hideReason(2, charging: false), isNull, reason: 'a confirmed drain is never re-hidden as flat');
  });

  test('a new charge clears an earlier confirmed drain', () {
    policy.onSample(3, charging: false);
    policy.onSample(2, charging: false);
    expect(policy.confirmedDrainForTesting, isTrue);
    policy.onCharging('omi', true);
    expect(policy.confirmedDrainForTesting, isFalse);
    advance(const Duration(minutes: 30));
    policy.onCharging('omi', false);
    policy.onSample(2, charging: false);
    expect(policy.hideReason(2, charging: false), BatteryHideReason.longCharge,
        reason: 'the reading stuck through the charge is not the drain seen before it');
  });

  test('first pairing hides a near-empty reading until a believable one arrives', () {
    policy.markFirstPairing('omi');
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), BatteryHideReason.firstPairing);
    policy.onSample(93, charging: false);
    expect(policy.hideReason(93, charging: false), isNull);
    policy.onSample(5, charging: false);
    expect(policy.hideReason(5, charging: false), isNull, reason: 'first-pairing suspicion ends with a real reading');
  });

  test('a long charge that ends near empty is hidden; a short one is not', () {
    policy.onCharging('omi', true);
    advance(const Duration(minutes: 5));
    policy.onCharging('omi', false);
    policy.onSample(2, charging: false);
    expect(policy.hideReason(2, charging: false), isNull);

    policy.onCharging('omi', true);
    advance(const Duration(minutes: 25));
    policy.onCharging('omi', false);
    expect(policy.hideReason(2, charging: false), BatteryHideReason.longCharge);
    advance(const Duration(hours: 3));
    policy.onSample(2, charging: false);
    expect(policy.hideReason(2, charging: false), BatteryHideReason.flat,
        reason: 'the long charge is too old to explain it; the flat rule still does');
  });

  test('a charge is not timed across a reconnect the app did not observe', () {
    policy.onCharging('omi', true);
    advance(const Duration(minutes: 40));
    policy.beginConnection('omi');
    policy.onCharging('omi', false);
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), isNull);
  });

  test('an observed long charge that ended is still known after a reconnect', () {
    policy.onCharging('omi', true);
    advance(const Duration(minutes: 40));
    policy.onCharging('omi', false);
    policy.beginConnection('omi');
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), BatteryHideReason.longCharge);
  });

  test('a real 0% clears a remembered stuck value', () {
    final store = InMemoryBatteryStuckStore()..save({'omi': (1, now)});
    final p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(0, charging: false);
    expect(store.load(), isEmpty);
    p.onSample(1, charging: false);
    expect(p.hideReason(1, charging: false), isNull);
  });

  test('a stuck reading is hidden at once on the next connection, until a real reading arrives', () {
    final store = InMemoryBatteryStuckStore();
    var p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(1, charging: false);
    advance(BatteryDisplayPolicy.flatHold);
    expect(p.hideReason(1, charging: false), BatteryHideReason.flat);
    p.rememberIfStuck(1, charging: false);

    // App restart: a fresh policy, same store.
    p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(1, charging: false);
    expect(p.hideReason(1, charging: false), BatteryHideReason.flat);
    expect(p.hideReason(2, charging: false), isNull, reason: 'only the exact stuck value is remembered');

    p.onSample(96, charging: false);
    p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(1, charging: false);
    expect(p.hideReason(1, charging: false), isNull, reason: 'a real reading cleared the record');
  });

  test('a remembered stuck reading expires after a week', () {
    final store = InMemoryBatteryStuckStore()..save({'omi': (1, now)});
    advance(BatteryDisplayPolicy.stuckMemory + const Duration(minutes: 1));
    final p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(1, charging: false);
    expect(p.hideReason(1, charging: false), isNull);
  });

  test('a falling reading clears a remembered stuck value', () {
    final store = InMemoryBatteryStuckStore()..save({'omi': (2, now)});
    final p = BatteryDisplayPolicy(clock: () => now, store: store)..beginConnection('omi');
    p.onSample(2, charging: false);
    expect(p.hideReason(2, charging: false), BatteryHideReason.flat);
    p.onSample(1, charging: false);
    expect(p.hideReason(1, charging: false), isNull);
    expect(store.load(), isEmpty);
  });

  test('history is per device', () {
    policy.markFirstPairing('other');
    policy.onSample(1, charging: false);
    expect(policy.hideReason(1, charging: false), isNull);
  });

  test('the kill switch shows every reading', () {
    policy.enabled = false;
    policy.markFirstPairing('omi');
    policy.onSample(1, charging: true);
    expect(policy.hideReason(1, charging: true), isNull);
    expect(policy.hideReason(1, charging: false), isNull);
    expect(policy.untilFlat(1, charging: false), isNull);
  });

  test('a real 0% always shows when not charging', () {
    policy.markFirstPairing('omi');
    policy.onSample(0, charging: false);
    expect(policy.hideReason(0, charging: false), isNull);
    expect(policy.untilFlat(0, charging: false), isNull);
  });

  test('unknown readings are never classified', () {
    expect(policy.hideReason(-1, charging: true), isNull);
    expect(policy.hideReason(-1, charging: false), isNull);
  });
}
