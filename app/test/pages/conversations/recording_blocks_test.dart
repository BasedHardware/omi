import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/conversations/recording_blocks.dart';
import 'package:omi/services/wals/wal.dart';

const _t0 = 1790000000;

Wal _wal(
  int start,
  int seconds, {
  WalStatus status = WalStatus.miss,
  WalStorage storage = WalStorage.disk,
  String device = 'pendant-a',
  int retryCount = 0,
}) =>
    Wal(
      timerStart: _t0 + start,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: status,
      storage: storage,
      device: device,
      retryCount: retryCount,
    );

List<Wal> _newestFirst(List<Wal> wals) => wals..sort((a, b) => b.timerStart.compareTo(a.timerStart));

void main() {
  test('back-to-back 75 s backup files read as one recording', () {
    // The screenshot in #20455's follow-up: 7:23, 7:24, 7:25, 7:26, 7:28.
    final wals = _newestFirst([for (var i = 0; i < 5; i++) _wal(i * 75, 75)]);

    final blocks = groupRecordingBlocks(wals);

    expect(blocks, hasLength(1));
    expect(blocks.single.wals, hasLength(5));
    expect(blocks.single.startSeconds, _t0);
    expect(blocks.single.seconds, 5 * 75);
  });

  test('3 minute device chunks join, and a pause longer than the gap splits', () {
    final wals = _newestFirst([
      _wal(0, 180, storage: WalStorage.sdcard),
      _wal(180, 180, storage: WalStorage.sdcard),
      _wal(360 + recordingBlockGapSeconds, 180, storage: WalStorage.sdcard),
      _wal(540 + recordingBlockGapSeconds + recordingBlockGapSeconds + 1, 180, storage: WalStorage.sdcard),
    ]);

    final blocks = groupRecordingBlocks(wals);

    expect([for (final b in blocks) b.wals.length], [1, 3]);
  });

  test('a different device or the device copy of phone audio never merges', () {
    final wals = _newestFirst([
      _wal(0, 75),
      _wal(75, 75, device: 'pendant-b'),
      _wal(150, 75, storage: WalStorage.sdcard),
    ]);

    expect(groupRecordingBlocks(wals), hasLength(3));
  });

  test('a block shows its most serious piece', () {
    final wals = _newestFirst([
      _wal(0, 75, status: WalStatus.synced),
      _wal(75, 75, status: WalStatus.outsideRecoveryWindow),
      _wal(150, 75, status: WalStatus.miss, retryCount: walMaxAutoRetries),
      _wal(225, 75, status: WalStatus.uploaded),
    ]);

    final block = groupRecordingBlocks(wals).single;

    expect(block.state, WalSyncDisplayState.failed);
    expect(block.representative.timerStart, _t0 + 150);
  });
}
