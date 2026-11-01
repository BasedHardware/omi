import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/services/wals/ring_storage_sync.dart';
import 'package:omi/utils/wal_sync_upload.dart';

/// The backend reads `_clke<run>_` directly before the trailing timestamp
/// (backend/utils/sync/clock_run.py); keep this in step with that pattern.
final _backendToken = RegExp(r'(?:^|_)clke([0-9a-z]{1,32})_[0-9.]+\.(?:bin|wav)$');

Wal _wal({String? clockRun}) =>
    Wal(timerStart: 1792157893, codec: BleAudioCodec.opus, seconds: 60, device: 'AA:BB:CC', clockRun: clockRun);

void main() {
  group('Wal clock run filename', () {
    test('device-clocked names are unchanged', () {
      expect(_wal().getFileName(), 'audio_aabbcc_${BleAudioCodec.opus}_16000_1_fs160_1792157893.bin');
    });

    test('an estimated clock names its run before the timestamp', () {
      final name = _wal(clockRun: 'k3x9').getFileName() as String;
      expect(name, 'audio_aabbcc_${BleAudioCodec.opus}_16000_1_fs160_clkek3x9_1792157893.bin');
      expect(_backendToken.firstMatch(name)?.group(1), 'k3x9');
      expect(isFramedWalSyncFileName(name), isTrue);
      // The trailing token is still the timestamp, as older backends parse it.
      expect(name.substring(0, name.length - 4).split('_').last, '1792157893');
    });

    test('per-chunk names carry the chunk run', () {
      final name = _wal().getFileNameByTimeStarts(1792157953, clockRun: 'r1') as String;
      expect(_backendToken.firstMatch(name)?.group(1), 'r1');
    });

    test('run survives persistence', () {
      final restored = Wal.fromJson(_wal(clockRun: 'k3x9').toJson());
      expect(restored.clockRun, 'k3x9');
      expect(Wal.fromJson(_wal().toJson()).clockRun, isNull);
    });

    test('new runs match the backend token alphabet', () {
      final run = Wal.newClockRun();
      expect(RegExp(r'^[0-9a-z]{1,32}$').hasMatch(run), isTrue);
      expect(Wal.newClockRun(), isNot(run));
    });
  });

  group('ringRecordClockBoundary', () {
    test('contiguous device-clocked records stay one recording', () {
      final b = ringRecordClockBoundary(previousTs: 1000, ts: 1001, rtcValid: true, currentRun: null);
      expect(b.breaks, isFalse);
      expect(b.run, isNull);
    });

    test('a forward gap (pendant off) breaks without inventing a run', () {
      final b = ringRecordClockBoundary(previousTs: 1000, ts: 1000 + 86400, rtcValid: true, currentRun: null);
      expect(b.breaks, isTrue);
      expect(b.run, isNull);
    });

    test('a backwards step (stale clock after restart) breaks into its own run', () {
      final b = ringRecordClockBoundary(previousTs: 5000, ts: 1000, rtcValid: true, currentRun: null);
      expect(b.breaks, isTrue);
      expect(b.run, isNotNull);
      final next = ringRecordClockBoundary(previousTs: 1000, ts: 1001, rtcValid: true, currentRun: b.run);
      expect(next.breaks, isFalse);
      expect(next.run, b.run);
      // The next discontinuity (e.g. the phone correcting the clock) ends it.
      final corrected = ringRecordClockBoundary(previousTs: 1001, ts: 9000, rtcValid: true, currentRun: b.run);
      expect(corrected.breaks, isTrue);
      expect(corrected.run, isNull);
    });

    test('without a valid RTC every record shares one estimated run', () {
      final first = ringRecordClockBoundary(previousTs: null, ts: 0, rtcValid: false, currentRun: null);
      expect(first.run, isNotNull);
      final second = ringRecordClockBoundary(previousTs: 0, ts: 0, rtcValid: false, currentRun: first.run);
      expect(second.breaks, isFalse);
      expect(second.run, first.run);
    });

    test('a device-clocked record after an untimed one starts a new recording', () {
      final b = ringRecordClockBoundary(previousTs: 0, ts: 1792157893, rtcValid: true, currentRun: 'est');
      expect(b.breaks, isTrue);
      expect(b.run, isNull);
    });
  });
}
