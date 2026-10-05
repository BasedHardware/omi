import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/wal.dart';

typedef WalEvidenceRun = ({int start, int end, bool claimable});

bool partitionsEvidenceRuns(bool darkWrite, BleAudioCodec codec, List<WalFrame> frames) =>
    darkWrite && (codec.isOpusSupported() || codec == BleAudioCodec.pcm16) && hasCaptureEvidence(frames);

bool walExtendsRun(Wal wal, WalEvidenceRun run, WalFrame first) => run.claimable
    ? wal.captureRoot == first.captureRoot &&
        wal.sourceClockEpoch == first.sourceClockEpoch &&
        wal.sourceFrameStart != null &&
        wal.sourceFrameStart! + wal.totalFrames == first.sourceFramePosition
    : wal.captureRoot == null;

bool _hasCaptureTriple(WalFrame frame) =>
    frame.captureRoot != null && frame.sourceFramePosition != null && frame.sourceClockEpoch != null;

bool hasCaptureEvidence(List<WalFrame> frames) => frames.any(_hasCaptureTriple);

bool _evidenceContinues(WalFrame prev, WalFrame next) =>
    _hasCaptureTriple(prev) &&
    next.captureRoot == prev.captureRoot &&
    next.sourceClockEpoch == prev.sourceClockEpoch &&
    next.sourceFramePosition == prev.sourceFramePosition! + 1;

({String? root, int? start, int? epoch}) stableCaptureEvidence(List<WalFrame> frames) {
  if (frames.isEmpty) return (root: null, start: null, epoch: null);
  final first = frames.first;
  final root = first.captureRoot;
  final start = first.sourceFramePosition;
  final epoch = first.sourceClockEpoch;
  final stable = root != null &&
      start != null &&
      epoch != null &&
      frames.asMap().entries.every(
            (entry) =>
                entry.value.captureRoot == root &&
                entry.value.sourceClockEpoch == epoch &&
                entry.value.sourceFramePosition == start + entry.key,
          );
  return stable ? (root: root, start: start, epoch: epoch) : (root: null, start: null, epoch: null);
}

int syncedPrefixCount(List<bool> synced) {
  var count = 0;
  for (final s in synced) {
    if (!s) break;
    count++;
  }
  return count;
}

List<WalEvidenceRun> walEvidenceRunRanges(List<WalFrame> frames) {
  final runs = <WalEvidenceRun>[];
  for (var i = 0; i < frames.length; i++) {
    if (runs.isEmpty) {
      runs.add((start: 0, end: 1, claimable: _hasCaptureTriple(frames[i])));
      continue;
    }
    final last = runs.last;
    final extendsRun = last.claimable ? _evidenceContinues(frames[i - 1], frames[i]) : !_hasCaptureTriple(frames[i]);
    if (extendsRun) {
      runs[runs.length - 1] = (start: last.start, end: i + 1, claimable: last.claimable);
    } else {
      runs.add((start: i, end: i + 1, claimable: _hasCaptureTriple(frames[i])));
    }
  }
  return runs;
}
