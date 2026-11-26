import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/mobile_held_wal_signal.dart';
import 'package:omi/services/wals/wal.dart';

final _now = DateTime.utc(2026, 11, 25, 18);
const _hour = Duration(hours: 1);

Wal _file({bool mobile = true, bool held = true, WalStatus status = WalStatus.miss}) => Wal(
      timerStart: _now.subtract(const Duration(minutes: 31)).millisecondsSinceEpoch ~/ 1000,
      seconds: 60,
      totalFrames: 50,
      codec: BleAudioCodec.opus,
      device: 'source',
      status: status,
      storage: WalStorage.disk,
      filePath: mobile ? 'audio_omimobilebatch_file.bin' : 'audio_other_file.bin',
      mobileBatchHold: held
          ? (sealedAtMs: _now.subtract(const Duration(seconds: 1400)).millisecondsSinceEpoch, state: 'bg300')
          : null,
    );

void main() {
  for (final enabled in [true, false]) {
    test('samples sealed backlog for the ${enabled ? 'enabled' : 'control'} cohort with bounded fields', () {
      fakeAsync((time) {
        final events = <Map<String, Object>>[];
        final signal = MobileHeldWalSignal(cohort: (_) async => enabled, emit: (event) => events.add(event.properties));
        signal.startup([
          _file(held: enabled),
          _file(held: enabled, status: WalStatus.uploadRejected),
          _file(status: WalStatus.uploaded),
          _file(mobile: false),
        ], _now);
        time.flushMicrotasks();
        expect(events.single, {
          'trigger': 'startup',
          'held_wal_count': 2,
          'oldest_held_age_s': enabled ? 1400 : 1800,
          'hold_flag_on': enabled,
          'hold_state': enabled ? 'bg300' : 'unknown',
          'cohort': enabled ? 'on' : 'off',
        });
      });
    });
  }

  test('one startup, one event on foreground, and one per hour even after a long suspension', () {
    fakeAsync((time) {
      final events = <Map<String, Object>>[];
      final signal = MobileHeldWalSignal(cohort: (_) async => true, emit: (event) => events.add(event.properties));
      signal.startup([], _now);
      signal.startup([], _now);
      signal.hourly([], _now.add(const Duration(minutes: 59)));
      time.flushMicrotasks();
      signal.foreground([], _now.add(_hour));
      signal.hourly([], _now.add(_hour));
      signal.hourly([], _now.add(_hour));
      time.flushMicrotasks();
      final resume = _now.add(const Duration(days: 2));
      signal.hourly([_file()], resume);
      signal.hourly([_file()], resume);
      time.flushMicrotasks();
      expect(events.map((event) => event['trigger']), ['startup', 'foreground', 'hourly', 'hourly']);
      expect(events.first['held_wal_count'], 0);
      expect(events.last['oldest_held_age_s'], 86400);
    });
  });

  test('cold start retains the pre-drain aggregate until the cohort is known', () {
    fakeAsync((time) {
      final events = <Map<String, Object>>[];
      var refreshes = 0;
      bool? enabled;
      final signal = MobileHeldWalSignal(
          cohort: (refresh) async {
            if (refresh) refreshes++;
            return enabled;
          },
          emit: (event) => events.add(event.properties));
      signal.startup([_file()], _now);
      time.flushMicrotasks();
      signal.hourly([], _now.add(const Duration(seconds: 10)));
      time.flushMicrotasks();
      expect(events, isEmpty);
      expect(refreshes, 1);
      enabled = true;
      signal.hourly([], _now.add(const Duration(seconds: 20)));
      time.flushMicrotasks();
      expect(events.single['trigger'], 'startup');
      expect(events.single['held_wal_count'], 1);
    });
  });

  test('an account switch drops queued aggregates from the previous owner', () {
    fakeAsync((time) {
      final events = <Map<String, Object>>[];
      final assignment = Completer<bool?>();
      final signal =
          MobileHeldWalSignal(cohort: (_) => assignment.future, emit: (event) => events.add(event.properties));
      signal.startup([_file()], _now);
      signal.clearUserData();
      assignment.complete(true);
      time.flushMicrotasks();
      signal.foreground([], _now);
      time.flushMicrotasks();
      expect(events.single['trigger'], 'foreground');
      expect(events.single['held_wal_count'], 0);
    });
  });
}
