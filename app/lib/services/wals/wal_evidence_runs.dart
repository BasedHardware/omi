import 'dart:math';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';

typedef WalEvidenceRun = ({int start, int end, bool claimable});

double walAudioSeconds(Wal wal) {
  if (wal.totalFrames > 0) {
    final framesPerSecond = wal.codec.getFramesPerSecond();
    if (framesPerSecond > 0) return wal.totalFrames / framesPerSecond;
  }
  return max(0, wal.seconds).toDouble();
}

bool partitionsEvidenceRuns(bool darkWrite, BleAudioCodec codec, List<WalFrame> frames) =>
    darkWrite && (codec.isOpusSupported() || codec == BleAudioCodec.pcm16) && hasCaptureEvidence(frames);

bool walExtendsRun(Wal wal, WalEvidenceRun run, WalFrame first) => run.claimable
    ? wal.captureRoot == first.captureRoot &&
        wal.sourceClockEpoch == first.sourceClockEpoch &&
        wal.sourceFrameStart != null &&
        wal.sourceFrameStart! + wal.totalFrames == first.sourceFramePosition
    : wal.captureRoot == null;

double captureSelectionStartSeconds(DateTime preciseEnd, int frameCount, int framesPerSecond) =>
    preciseEnd.microsecondsSinceEpoch / 1000000 - frameCount / framesPerSecond;

String walEvidenceRunFileName(Wal wal, double selectionStartSeconds, int frameOffset, int framesPerSecond) {
  if (framesPerSecond <= 0) return wal.getFileName();
  var token = (selectionStartSeconds + frameOffset / framesPerSecond).toStringAsFixed(6);
  if (token.contains('.')) {
    token = token.replaceAll(RegExp(r'0+$'), '').replaceAll(RegExp(r'\.$'), '');
  }
  return wal.getFileName().replaceAll(RegExp(r'_\d+\.bin$'), '_$token.bin');
}

String walCollisionName(String name, int sequence, bool beforeTimestamp) {
  final dot = name.lastIndexOf('.');
  final stem = dot > 0 ? name.substring(0, dot) : name;
  final ext = dot > 0 ? name.substring(dot) : '';
  final lastUnderscore = beforeTimestamp ? stem.lastIndexOf('_') : -1;
  if (lastUnderscore < 0) return '${stem}_u$sequence$ext';
  return '${stem.substring(0, lastUnderscore)}_u$sequence${stem.substring(lastUnderscore)}$ext';
}

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

({int? start, int? end, int? ringId, int? epoch}) stableLiveWalEvidence(
    List<WalFrame> frames, String? deviceId, PendantRingCustody custody) {
  const none = (start: null, end: null, ringId: null, epoch: null);
  if (frames.isEmpty ||
      !frames.every((f) => f.liveOrdinal != null && f.connectionEpoch != null && f.liveRingId != null)) {
    return none;
  }
  final first = frames.first.liveOrdinal!;
  final ordered = frames.asMap().entries.every((e) => e.value.liveOrdinal == first + e.key);
  final epochs = frames.map((f) => f.connectionEpoch).toSet();
  final ringIds = frames.map((f) => f.liveRingId).toSet();
  if (!ordered || epochs.length != 1 || ringIds.length != 1) return none;
  if (deviceId == null) return none;
  final ringId = custody.currentRingId(deviceId);
  if (ringId == null || ringIds.first != ringId) return none;
  if (frames.first.connectionEpoch != custody.latestEpoch(deviceId)) return none;
  return (start: first, end: first + frames.length, ringId: ringId, epoch: frames.first.connectionEpoch);
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
