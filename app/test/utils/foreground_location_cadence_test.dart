import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/audio/foreground.dart';

void main() {
  final t0 = DateTime.utc(2026, 10, 21, 12);

  test('first repeat refreshes location', () {
    expect(backgroundLocationRefreshDue(null, t0), isTrue);
  });

  test('repeats inside the refresh interval skip location', () {
    expect(backgroundLocationRefreshDue(t0, t0.add(const Duration(minutes: 5))), isFalse);
    expect(backgroundLocationRefreshDue(t0, t0.add(const Duration(minutes: 10))), isFalse);
    expect(backgroundLocationRefreshDue(t0, t0.add(const Duration(minutes: 14, seconds: 59))), isFalse);
  });

  test('a repeat at the interval refreshes location', () {
    expect(backgroundLocationRefreshDue(t0, t0.add(backgroundLocationRefreshInterval)), isTrue);
    expect(backgroundLocationRefreshDue(t0, t0.add(const Duration(minutes: 20))), isTrue);
  });

  test('a wall-clock rollback does not starve location', () {
    expect(backgroundLocationRefreshDue(t0, t0.subtract(const Duration(minutes: 1))), isTrue);
  });

  test('the interval stays inside the backend geolocation cache TTL', () {
    expect(backgroundLocationRefreshInterval, lessThan(const Duration(minutes: 30)));
  });

  test('the WAL sync wake is sent on every repeat, before the location gate', () {
    final source = File('lib/utils/audio/foreground.dart').readAsStringSync();
    final repeat = source.substring(source.indexOf('void onRepeatEvent'));
    final wake = repeat.indexOf("sendDataToMain({'recordingSyncWake': true})");
    final gate = repeat.indexOf('backgroundLocationRefreshDue');
    expect(wake, greaterThan(0));
    expect(gate, greaterThan(wake));
    expect(source, contains('ForegroundTaskEventAction.repeat(60 * 1000 * 5)'));
  });
}
