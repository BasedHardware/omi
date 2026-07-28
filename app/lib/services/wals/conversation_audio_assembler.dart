import 'dart:io';
import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/wal.dart';

typedef OpusSilenceFrameFactory = List<int> Function(BleAudioCodec codec);

class ConversationAudioPart {
  const ConversationAudioPart({
    required this.wal,
    required this.file,
  });

  final Wal wal;
  final File file;
}

class ConversationAudioAssembly {
  const ConversationAudioAssembly({
    required this.file,
    required this.timerStart,
    required this.totalFrames,
    required this.hadLiveGap,
    required this.sourceWals,
  });

  final File file;
  final int timerStart;
  final int totalFrames;
  final bool hadLiveGap;
  final List<Wal> sourceWals;
}

/// Builds the one canonical phone-side recording for a completed pendant
/// conversation.
///
/// Source WALs are immutable durability records. They are ordered by the
/// pendant's sequence, validated as length-prefixed Opus, and copied into one
/// file. Timestamp discontinuities shorter than the conversation boundary are
/// represented by encoded silence so a recovered gap keeps its wall-clock
/// position instead of compressing the transcript timeline.
Future<ConversationAudioAssembly> assembleConversationAudio({
  required List<ConversationAudioPart> parts,
  required File destination,
  required OpusSilenceFrameFactory silenceFrameFactory,
  int conversationBoundarySeconds = 120,
}) async {
  if (parts.isEmpty) {
    throw ArgumentError.value(parts, 'parts', 'must not be empty');
  }

  final orderedSources = List<ConversationAudioPart>.from(parts)
    ..sort((left, right) {
      final leftRange = RingProtocol.parseRecoverySourceRange(left.wal.sourceId);
      final rightRange = RingProtocol.parseRecoverySourceRange(right.wal.sourceId);
      if (leftRange == null || rightRange == null) {
        throw StateError('Canonical assembly requires pendant sequence identity');
      }
      final startCompare = leftRange.start.compareTo(rightRange.start);
      if (startCompare != 0) return startCompare;
      return rightRange.end.compareTo(leftRange.end);
    });

  final formatReference = orderedSources.first.wal;
  if (!formatReference.codec.isOpusSupported()) {
    throw StateError('Canonical assembly supports Opus pendant audio only');
  }
  final fps = formatReference.codec.getFramesPerSecond();
  if (fps <= 0) {
    throw StateError('Canonical assembly requires a positive frame rate');
  }

  for (final part in orderedSources) {
    final wal = part.wal;
    final range = RingProtocol.parseRecoverySourceRange(wal.sourceId);
    if (range == null) {
      throw StateError('Canonical assembly requires pendant sequence identity');
    }
    if (wal.device != formatReference.device ||
        wal.codec != formatReference.codec ||
        wal.sampleRate != formatReference.sampleRate ||
        wal.channel != formatReference.channel ||
        wal.frameSize != formatReference.frameSize) {
      throw StateError('Canonical assembly found incompatible audio formats');
    }
  }

  /*
   * Reconnect replay can durably rediscover a range using different timestamp
   * chunk boundaries. For example, [10, 20) + [20, 30) may later be replayed
   * as [10, 30). The sequence union is identical, but treating every immutable
   * durability artifact as independent audio duplicates speech and permanently
   * blocks canonical assembly.
   *
   * Remove a source only when the remaining sources still cover its complete
   * sequence range. Longest-first removal resolves both containing replays and
   * crossing replay ranges while preserving the exact union. Any irreducible
   * partial overlap still fails closed below.
   */
  final ordered = List<ConversationAudioPart>.from(orderedSources);
  final removalCandidates = List<ConversationAudioPart>.from(orderedSources)
    ..sort((left, right) {
      final leftRange = RingProtocol.parseRecoverySourceRange(left.wal.sourceId)!;
      final rightRange = RingProtocol.parseRecoverySourceRange(right.wal.sourceId)!;
      return (rightRange.end - rightRange.start).compareTo(
        leftRange.end - leftRange.start,
      );
    });
  for (final candidate in removalCandidates) {
    if (!ordered.any((part) => identical(part, candidate))) continue;
    final candidateRange = RingProtocol.parseRecoverySourceRange(candidate.wal.sourceId)!;
    final remainingCoverage = RingSequenceCoverage(
      ordered
          .where((part) => !identical(part, candidate))
          .map((part) => RingProtocol.parseRecoverySourceRange(part.wal.sourceId)!),
    );
    if (remainingCoverage.covers(candidateRange.start, candidateRange.end)) {
      ordered.removeWhere((part) => identical(part, candidate));
    }
  }

  var expectedSequence = RingProtocol.parseRecoverySourceRange(ordered.first.wal.sourceId)!.start;
  var hadLiveGap = orderedSources.any((part) => part.wal.status == WalStatus.miss);
  for (final part in ordered) {
    final range = RingProtocol.parseRecoverySourceRange(part.wal.sourceId)!;
    if (range.start < expectedSequence) {
      throw StateError('Canonical assembly found irreducible overlapping pendant sequence');
    }
    hadLiveGap = hadLiveGap || range.start > expectedSequence;
    expectedSequence = range.end;
  }
  final first = ordered.first.wal;

  final partial = File('${destination.path}.partial');
  if (await destination.exists()) await destination.delete();
  if (await partial.exists()) await partial.delete();

  final sink = partial.openWrite();
  var sinkClosed = false;
  var totalFrames = 0;
  List<int>? silenceFrame;

  try {
    for (final part in ordered) {
      final wal = part.wal;
      final expectedStart = first.timerStart + totalFrames / fps;
      final gapSeconds = wal.timerStart - expectedStart;
      if (gapSeconds >= conversationBoundarySeconds) {
        throw StateError('Canonical assembly crossed a conversation boundary');
      }
      final silenceFrames = gapSeconds > 0 ? (gapSeconds * fps).round() : 0;
      if (silenceFrames > 0) {
        silenceFrame ??= silenceFrameFactory(first.codec);
        if (silenceFrame.isEmpty) {
          throw StateError('Canonical assembly could not encode silence');
        }
        final prefix = _lengthPrefix(silenceFrame.length);
        for (var index = 0; index < silenceFrames; index++) {
          sink.add(prefix);
          sink.add(silenceFrame);
        }
        totalFrames += silenceFrames;
      }

      final bytes = await part.file.readAsBytes();
      final framesInFile = _validateLengthPrefixedOpus(bytes);
      if (wal.totalFrames > 0 && framesInFile != wal.totalFrames) {
        throw StateError('Canonical assembly frame count does not match its WAL');
      }
      sink.add(bytes);
      totalFrames += framesInFile;
      hadLiveGap = hadLiveGap || wal.status == WalStatus.miss;
    }

    await sink.flush();
    await sink.close();
    sinkClosed = true;
    await partial.rename(destination.path);
  } catch (_) {
    if (!sinkClosed) {
      try {
        await sink.close();
      } catch (_) {
        // Preserve the assembly failure; cleanup is best-effort.
      }
    }
    if (await partial.exists()) await partial.delete();
    if (await destination.exists()) await destination.delete();
    rethrow;
  }

  return ConversationAudioAssembly(
    file: destination,
    timerStart: first.timerStart,
    totalFrames: totalFrames,
    hadLiveGap: hadLiveGap,
    sourceWals: orderedSources.map((part) => part.wal).toList(growable: false),
  );
}

Uint8List _lengthPrefix(int length) {
  final prefix = ByteData(4)..setUint32(0, length, Endian.little);
  return prefix.buffer.asUint8List();
}

int _validateLengthPrefixedOpus(Uint8List bytes) {
  var offset = 0;
  var frames = 0;
  while (offset < bytes.length) {
    if (bytes.length - offset < 4) {
      throw StateError('Canonical assembly found a truncated frame prefix');
    }
    final length = ByteData.sublistView(bytes, offset, offset + 4).getUint32(0, Endian.little);
    offset += 4;
    if (length <= 0 || length > 65536 || offset + length > bytes.length) {
      throw StateError('Canonical assembly found an invalid Opus frame');
    }
    offset += length;
    frames++;
  }
  if (frames == 0) {
    throw StateError('Canonical assembly found no Opus frames');
  }
  return frames;
}
