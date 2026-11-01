import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/audio/background_location_cadence.dart';

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

  test('the handler cannot backdate the stamp', () {
    final source = File('lib/utils/audio/foreground.dart').readAsStringSync();
    expect(source, isNot(contains('recordStart')));
    expect(source, isNot(contains('runBackgroundRepeat')));
    expect(source, isNot(contains('backgroundLocationRefreshDue')));
    expect('_locationCadence.onRepeat'.allMatches(source), hasLength(1));
    expect('_locationCadence.onStart'.allMatches(source), hasLength(1));
    final repeat = source.substring(source.indexOf('void onRepeatEvent'), source.indexOf('Future<void> onDestroy'));
    expect(repeat, contains('_locationCadence.onRepeat'));
    expect(repeat, isNot(contains('lastAttempt:')));
    expect(repeat, isNot(contains('attemptAt')));
    expect(repeat, isNot(contains('_locationInBackground(')));
    expect(repeat, contains("sendDataToMain({'recordingSyncWake': true})"));
    expect(source, contains('ForegroundTaskEventAction.repeat(60 * 1000 * 5)'));
  });

  test('the stored cadence skips a 5-minute repeat and refreshes at 15', () async {
    final cadence = BackgroundLocationCadence();
    var wakes = 0;
    var refreshes = 0;
    Future<void> refresh() async {
      refreshes++;
    }

    await cadence.onRepeat(
      now: t0,
      sendSyncWake: () => wakes++,
      refreshLocation: refresh,
    );
    expect(cadence.attemptAt, t0);
    expect(refreshes, 1);

    await cadence.onRepeat(
      now: t0.add(const Duration(minutes: 5)),
      sendSyncWake: () => wakes++,
      refreshLocation: refresh,
    );
    expect(wakes, 2);
    expect(refreshes, 1);
    expect(cadence.attemptAt, t0);

    await cadence.onRepeat(
      now: t0.add(backgroundLocationRefreshInterval),
      sendSyncWake: () => wakes++,
      refreshLocation: refresh,
    );
    expect(refreshes, 2);
    expect(cadence.attemptAt, t0.add(backgroundLocationRefreshInterval));
  });

  test('a 5-minute repeat sends the wake and does not refresh location', () async {
    var wakes = 0;
    var refreshes = 0;
    DateTime? recorded = t0;
    await runBackgroundRepeat(
      lastAttempt: t0,
      now: t0.add(const Duration(minutes: 5)),
      sendSyncWake: () => wakes++,
      recordAttempt: (attemptAt) => recorded = attemptAt,
      refreshLocation: () async => refreshes++,
    );
    expect(wakes, 1);
    expect(refreshes, 0);
    expect(recorded, t0);
  });

  test('a 15-minute repeat sends the wake, stamps the attempt, then refreshes', () async {
    var wakes = 0;
    DateTime? recorded = t0;
    final order = <String>[];
    final now = t0.add(backgroundLocationRefreshInterval);
    await runBackgroundRepeat(
      lastAttempt: t0,
      now: now,
      sendSyncWake: () {
        wakes++;
        order.add('wake');
      },
      recordAttempt: (attemptAt) {
        recorded = attemptAt;
        order.add('stamp');
      },
      refreshLocation: () async => order.add('refresh'),
    );
    expect(wakes, 1);
    expect(recorded, now);
    expect(order, ['wake', 'stamp', 'refresh']);
  });

  test('a failed refresh still keeps the attempt stamp', () async {
    DateTime? recorded = t0;
    final now = t0.add(const Duration(minutes: 20));
    await expectLater(
      runBackgroundRepeat(
        lastAttempt: t0,
        now: now,
        sendSyncWake: () {},
        recordAttempt: (attemptAt) => recorded = attemptAt,
        refreshLocation: () async => throw StateError('fix failed'),
      ),
      throwsStateError,
    );
    expect(recorded, now);
  });
}
