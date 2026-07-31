import 'dart:io';
import 'dart:typed_data';

import 'package:opus_dart/opus_dart.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/wal.dart';

typedef OpusSilenceFrameFactory = List<int> Function(BleAudioCodec codec);

/// Encodes one silent Opus frame in the same format used by CV1 capture.
///
/// Conversation assembly and user-visible playback must share this encoder so
/// an on-demand preview cannot compress wall-clock gaps differently from the
/// canonical upload artifact.
List<int> encodeOpusSilenceFrame(BleAudioCodec codec) {
  final encoder = SimpleOpusEncoder(
    sampleRate: 16000,
    channels: 1,
    application: Application.voip,
  );
  try {
    return encoder.encode(
      input: Int16List(codec.getFrameSize()),
    );
  } finally {
    encoder.destroy();
  }
}

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
    required this.captureEndSeconds,
    required this.hadLiveGap,
    required this.sourceWals,
  });

  final File file;
  final int timerStart;
  final int totalFrames;
  final double captureEndSeconds;
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

  final rangedSources = parts.map((part) {
    final range = RingProtocol.parseRecoverySourceRange(part.wal.sourceId);
    if (range == null) {
      throw StateError('Canonical assembly requires pendant sequence identity');
    }
    return _RangedConversationAudioPart(
      part: part,
      start: range.start,
      end: range.end,
    );
  }).toList()
    ..sort(_compareRangedParts);
  final orderedSources = rangedSources.map((source) => source.part).toList(growable: false);

  final formatReference = orderedSources.first.wal;
  if (!formatReference.codec.isOpusSupported()) {
    throw StateError('Canonical assembly supports Opus pendant audio only');
  }
  final fps = formatReference.codec.getFramesPerSecond();
  if (fps <= 0) {
    throw StateError('Canonical assembly requires a positive frame rate');
  }

  for (final source in rangedSources) {
    final wal = source.part.wal;
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
   * chunk boundaries. Select a non-overlapping path that tiles each contiguous
   * sequence-union component exactly. Greedily removing a covered artifact is
   * unsafe: removing [10, 20) from [10, 20), [10, 15), [15, 21), [20, 30)
   * leaves an overlap even though [10, 20) + [20, 30) is a lossless tiling.
   *
   * Every immutable source remains in [sourceWals] for lifecycle accounting;
   * only the exact tiling is copied into the canonical audio file. A component
   * without an exact tiling fails closed rather than duplicating or dropping
   * pendant sequence.
   */
  final ordered = _selectExactSequenceTiling(rangedSources);

  var expectedSequence = ordered.first.start;
  var hadLiveGap = orderedSources.any((part) => part.wal.status == WalStatus.miss);
  for (final source in ordered) {
    if (source.start < expectedSequence) {
      throw StateError('Canonical assembly found irreducible overlapping pendant sequence');
    }
    hadLiveGap = hadLiveGap || source.start > expectedSequence;
    expectedSequence = source.end;
  }
  final first = ordered.first.part.wal;

  final partial = File('${destination.path}.partial');
  if (await destination.exists()) await destination.delete();
  if (await partial.exists()) await partial.delete();

  final sink = partial.openWrite();
  var sinkClosed = false;
  var totalFrames = 0;
  List<int>? silenceFrame;
  _RangedConversationAudioPart? previousSource;

  try {
    for (final source in ordered) {
      final part = source.part;
      final wal = part.wal;
      final previousWal = previousSource?.part.wal;
      final wallGapSeconds = previousWal == null ? 0 : wal.timerStart - previousWal.wallClockEndSeconds;
      if (wallGapSeconds >= conversationBoundarySeconds) {
        throw StateError('Canonical assembly crossed a conversation boundary');
      }
      final expectedStart = first.timerStart + totalFrames / fps;
      final gapSeconds = wal.timerStart - expectedStart;
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
      previousSource = source;
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
    captureEndSeconds: ordered.map((source) => source.part.wal.wallClockEndSeconds).reduce(
          (left, right) => left > right ? left : right,
        ),
    hadLiveGap: hadLiveGap,
    sourceWals: orderedSources.map((part) => part.wal).toList(growable: false),
  );
}

class _RangedConversationAudioPart {
  const _RangedConversationAudioPart({
    required this.part,
    required this.start,
    required this.end,
  });

  final ConversationAudioPart part;
  final int start;
  final int end;
}

class _TilingState {
  const _TilingState.root()
      : previous = null,
        source = null,
        partCount = 0,
        syncedCount = 0;

  _TilingState.extend(
    _TilingState predecessor,
    _RangedConversationAudioPart next,
  )   : previous = predecessor,
        source = next,
        partCount = predecessor.partCount + 1,
        syncedCount = predecessor.syncedCount + (next.part.wal.status == WalStatus.synced ? 1 : 0);

  final _TilingState? previous;
  final _RangedConversationAudioPart? source;
  final int partCount;
  final int syncedCount;
}

int _compareRangedParts(
  _RangedConversationAudioPart left,
  _RangedConversationAudioPart right,
) {
  final startCompare = left.start.compareTo(right.start);
  if (startCompare != 0) return startCompare;
  final endCompare = left.end.compareTo(right.end);
  if (endCompare != 0) return endCompare;
  final statusCompare = _statusPreference(left.part.wal.status).compareTo(
    _statusPreference(right.part.wal.status),
  );
  if (statusCompare != 0) return statusCompare;
  final sourceCompare = left.part.wal.sourceId!.compareTo(right.part.wal.sourceId!);
  if (sourceCompare != 0) return sourceCompare;
  return left.part.file.path.compareTo(right.part.file.path);
}

int _statusPreference(WalStatus status) {
  if (status == WalStatus.synced) return 0;
  return status.index + 1;
}

List<_RangedConversationAudioPart> _selectExactSequenceTiling(
  List<_RangedConversationAudioPart> orderedSources,
) {
  final selected = <_RangedConversationAudioPart>[];
  var componentStart = 0;
  while (componentStart < orderedSources.length) {
    var componentEnd = componentStart + 1;
    var unionEnd = orderedSources[componentStart].end;
    while (componentEnd < orderedSources.length && orderedSources[componentEnd].start <= unionEnd) {
      if (orderedSources[componentEnd].end > unionEnd) {
        unionEnd = orderedSources[componentEnd].end;
      }
      componentEnd++;
    }

    final component = orderedSources.sublist(componentStart, componentEnd);
    final bestAt = <int, _TilingState>{
      component.first.start: const _TilingState.root(),
    };
    for (final source in component) {
      final prefix = bestAt[source.start];
      if (prefix == null) continue;
      final candidate = _TilingState.extend(prefix, source);
      final incumbent = bestAt[source.end];
      if (incumbent == null || _compareTilingStates(candidate, incumbent) < 0) {
        bestAt[source.end] = candidate;
      }
    }

    final winner = bestAt[unionEnd];
    if (winner == null) {
      throw StateError('Canonical assembly found irreducible overlapping pendant sequence');
    }
    final reversedTiling = <_RangedConversationAudioPart>[];
    _TilingState? cursor = winner;
    while (cursor?.source != null) {
      reversedTiling.add(cursor!.source!);
      cursor = cursor.previous;
    }
    selected.addAll(reversedTiling.reversed);
    componentStart = componentEnd;
  }
  return selected;
}

int _compareTilingStates(_TilingState left, _TilingState right) {
  final lengthCompare = left.partCount.compareTo(right.partCount);
  if (lengthCompare != 0) return lengthCompare;

  final syncedCompare = right.syncedCount.compareTo(left.syncedCount);
  if (syncedCompare != 0) return syncedCompare;

  /*
   * Both paths have the same length. Walking from leaf to root and replacing
   * the comparison whenever an earlier part differs produces the same result
   * as a forward lexicographic comparison without allocating either prefix.
   */
  var lexicographicCompare = 0;
  _TilingState? leftCursor = left;
  _TilingState? rightCursor = right;
  while (leftCursor?.source != null && rightCursor?.source != null) {
    final sourceCompare = _compareRangedParts(
      leftCursor!.source!,
      rightCursor!.source!,
    );
    if (sourceCompare != 0) {
      lexicographicCompare = sourceCompare;
    }
    leftCursor = leftCursor.previous;
    rightCursor = rightCursor.previous;
  }
  return lexicographicCompare;
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
