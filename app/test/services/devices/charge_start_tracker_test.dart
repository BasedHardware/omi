import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/charge_start_tracker.dart';

void main() {
  test('failed reads preserve the last successful charging observation', () {
    final tracker = ChargeStartTracker();
    expect(tracker.observe('omi', true), true);
    expect(tracker.observe('omi', null), false);
    expect(tracker.observe('omi', true), false);
    expect(tracker.observe('omi', null), false);
    expect(tracker.observe('omi', false), false);
    expect(tracker.observe('omi', null), false);
    expect(tracker.observe('omi', true), true);
  });

  test('unknown first read does not prevent a first successful charging edge', () {
    final tracker = ChargeStartTracker();
    expect(tracker.observe('omi', null), false);
    expect(tracker.observe('omi', true), true);
  });

  test('charge starts resume once, including background, but reconnect reads do not', () {
    final tracker = ChargeStartTracker();
    expect(tracker.observe('omi', false), false);
    expect(tracker.observe('omi', true), true);
    expect(tracker.observe('omi', true), false);
    expect(tracker.observe('omi', true), false, reason: 'reconnect while still charging');
    expect(tracker.observe('omi', false), false);
    expect(tracker.observe('omi', true), true);
    expect(tracker.observe('other', true), true);
  });
}
