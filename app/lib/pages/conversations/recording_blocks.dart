import 'package:omi/services/wals/wal.dart';

/// Offline Sync lists recordings, not backup files. Capture writes a file every
/// 75 s on the phone and the device hands storage over in fixed chunks, so one
/// continuous recording used to read as a column of identical 1–3 minute rows.
///
/// A gap shorter than this joins two files into one recording. It matches the
/// backend's default `conversation_timeout`: a pause short enough not to end a
/// conversation does not end a recording either.
const recordingBlockGapSeconds = 120;

/// One continuous recording made of one or more consecutive files.
class RecordingBlock {
  RecordingBlock(this.wals) : assert(wals.isNotEmpty);

  /// Newest first, like the list it came from.
  final List<Wal> wals;

  Wal get oldest => wals.last;

  int get startSeconds => oldest.timerStart;

  int get seconds {
    final end = wals.map((w) => w.timerStart + w.seconds).reduce((a, b) => a > b ? a : b);
    return end - startSeconds;
  }

  /// The piece whose state the row shows: the most serious one, so a block is
  /// never reported healthier than its worst part.
  Wal get representative => wals.reduce((a, b) => _rank(b.syncDisplayState) > _rank(a.syncDisplayState) ? b : a);

  WalSyncDisplayState get state => representative.syncDisplayState;
}

/// Higher is more serious. A switch, not a list, so a new state cannot compile
/// without a rank and silently read as the healthiest.
int _rank(WalSyncDisplayState state) => switch (state) {
      WalSyncDisplayState.synced => 0,
      WalSyncDisplayState.uploaded => 1,
      WalSyncDisplayState.waiting => 2,
      WalSyncDisplayState.syncing => 3,
      WalSyncDisplayState.retrying => 4,
      WalSyncDisplayState.outsideRecoveryWindow => 5,
      WalSyncDisplayState.unsupportedAudio => 6,
      WalSyncDisplayState.corrupted => 7,
      WalSyncDisplayState.uploadRejected => 8,
      WalSyncDisplayState.failed => 9,
    };

bool _onDevice(Wal wal) => wal.storage == WalStorage.sdcard || wal.storage == WalStorage.flashPage;

/// Groups [newestFirst] into recordings. A file joins the open block from the
/// same device and the same place (on the device or on the phone — the same
/// audio can exist in both) when it ends within [recordingBlockGapSeconds] of
/// where that block's oldest file starts. Each device and place keeps its own
/// open block, because their files interleave in newest-first order.
List<RecordingBlock> groupRecordingBlocks(List<Wal> newestFirst) {
  final blocks = <List<Wal>>[];
  final open = <(String, bool), List<Wal>>{};
  for (final wal in newestFirst) {
    final key = (wal.device, _onDevice(wal));
    final current = open[key];
    final next = current?.last;
    final joins = next != null &&
        wal.timerStart <= next.timerStart &&
        next.timerStart - (wal.timerStart + wal.seconds) <= recordingBlockGapSeconds;
    if (joins) {
      current!.add(wal);
    } else {
      blocks.add(open[key] = [wal]);
    }
  }
  return [for (final wals in blocks) RecordingBlock(wals)];
}
