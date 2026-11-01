import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;

import 'package:omi/utils/audio/pcm_wav_header.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/utils/logger.dart';

typedef OpusFrameDecoder = Int16List Function(Uint8List frame, int sampleRate, int channels);

/// Send only data, never platform objects or the player/its capture state.
class WalWavWorkItem {
  final String walId;
  final String? cachedWavPath;
  final String? inputPath;
  final List<List<int>> memoryFrames;
  final String? tempDirectory;
  final bool isOpus;
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final OpusFrameDecoder? opusFrameDecoder;

  const WalWavWorkItem.cached({required this.walId, required this.cachedWavPath})
      : inputPath = null,
        memoryFrames = const [],
        tempDirectory = null,
        isOpus = false,
        sampleRate = 0,
        channels = 0,
        bitsPerSample = 0,
        opusFrameDecoder = null;

  const WalWavWorkItem.decode({
    required this.walId,
    required this.inputPath,
    required this.memoryFrames,
    required this.tempDirectory,
    required this.isOpus,
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    this.opusFrameDecoder,
  }) : cachedWavPath = null;
}

class RecordingWavJob {
  final List<WalWavWorkItem> items;
  final String outputPath;
  final String tempDirectory;
  const RecordingWavJob({required this.items, required this.outputPath, required this.tempDirectory});
}

class IsolateWavResult {
  final String? path;
  final String? isolateName;
  IsolateWavResult(String? path) : this._(path, Isolate.current.debugName);
  const IsolateWavResult._(this.path, this.isolateName);
}

Future<IsolateWavResult> decodeWalWorkItemInIsolate(WalWavWorkItem item) async {
  final scratch = await Directory(item.tempDirectory!).createTemp('omi-audio-');
  try {
    final path = await _decodeToWav(item, '${scratch.path}/part.wav');
    if (path == null) return IsolateWavResult(null);
    // A unique, complete output survives for playback/share. Only job-owned scratch is removed.
    final published = await File(path).rename('${scratch.path}.wav');
    return IsolateWavResult(published.path);
  } finally {
    await scratch.delete(recursive: true);
  }
}

Future<IsolateWavResult> buildRecordingWavInIsolate(RecordingWavJob job) async {
  final scratch = await Directory(job.tempDirectory).createTemp('omi-recording-parts-');
  try {
    final parts = <File>[];
    for (var i = 0; i < job.items.length; i++) {
      final path = await _decodeToWav(job.items[i], '${scratch.path}/$i.wav');
      if (path != null) parts.add(File(path));
    }
    if (parts.isEmpty) return IsolateWavResult(null);
    final result = await WavCombiner.combineWavFiles(parts, job.outputPath);
    return IsolateWavResult(result.path);
  } finally {
    // Inputs and playback-cache files live outside this directory and are never deleted.
    await scratch.delete(recursive: true);
  }
}

/// Incremental WAL framing: preserve complete frames before a truncated tail, while keeping
/// memory proportional to a frame/chunk rather than the duration of a recording.
Stream<Uint8List> readLengthPrefixedFrames(Stream<List<int>> chunks) async* {
  final prefix = Uint8List(4);
  var prefixBytes = 0;
  int? length;
  final payload = BytesBuilder(copy: false);
  await for (final chunk in chunks) {
    var offset = 0;
    while (offset < chunk.length) {
      if (length == null) {
        while (prefixBytes < 4 && offset < chunk.length) {
          prefix[prefixBytes++] = chunk[offset++];
        }
        if (prefixBytes < 4) continue;
        length = ByteData.sublistView(prefix).getUint32(0, Endian.little);
        prefixBytes = 0;
      }
      final remaining = length - payload.length;
      final count = remaining < chunk.length - offset ? remaining : chunk.length - offset;
      if (count > 0) {
        payload.add(chunk.sublist(offset, offset + count));
        offset += count;
      }
      if (payload.length == length) {
        yield payload.takeBytes();
        length = null;
      }
    }
  }
}

bool _opusInitialized = false;

Future<void> _ensureOpusInitialized() async {
  if (_opusInitialized) return;
  // libopus state belongs to this isolate. The pinned plugin's loader uses FFI on
  // Android/iOS; it does not need a main-isolate method channel.
  // A newly spawned isolate has no opus_dart library binding yet. Initialize it
  // unconditionally once at this job boundary instead of probing an unbound late variable.
  initOpus(await opus_flutter.load());
  _opusInitialized = true;
}

Future<String?> _decodeToWav(WalWavWorkItem item, String outputPath) async {
  if (item.cachedWavPath != null) {
    return await File(item.cachedWavPath!).exists() ? item.cachedWavPath : null;
  }
  final inputPath = item.inputPath;
  if (inputPath != null && !await File(inputPath).exists()) return null;
  final frames = inputPath != null
      ? readLengthPrefixedFrames(File(inputPath).openRead())
      : Stream<Uint8List>.fromIterable(item.memoryFrames.map(Uint8List.fromList));
  SimpleOpusDecoder? nativeDecoder;
  RandomAccessFile? output;
  var dataSize = 0;
  final pending = BytesBuilder(copy: false);
  try {
    await for (final frame in frames) {
      // libopus interprets a zero-byte packet as packet loss and synthesizes audio.
      // Empty WAL payloads contain no recording; never turn them into concealment samples.
      if (frame.isEmpty) continue;
      Uint8List pcm;
      if (item.isOpus) {
        if (item.opusFrameDecoder == null && nativeDecoder == null) {
          await _ensureOpusInitialized();
          nativeDecoder = SimpleOpusDecoder(sampleRate: item.sampleRate, channels: item.channels);
        }
        try {
          final decoded = item.opusFrameDecoder != null
              ? item.opusFrameDecoder!(frame, item.sampleRate, item.channels)
              : nativeDecoder!.decode(input: frame);
          // Copy before the next native decode, honoring a decoder's typed-list view bounds.
          pcm = Uint8List.fromList(decoded.buffer.asUint8List(decoded.offsetInBytes, decoded.lengthInBytes));
        } catch (e) {
          // Existing behavior: retain good frames around a corrupt Opus packet.
          Logger.debug('AudioPlayerUtils: skipping corrupted Opus frame for WAL ${item.walId}: $e');
          continue;
        }
      } else {
        pcm = frame;
      }
      if (pcm.isEmpty) continue;
      output ??= await File(outputPath).open(mode: FileMode.write);
      if (dataSize == 0) await output.writeFrom(Uint8List(44));
      pending.add(pcm);
      dataSize += pcm.length;
      if (pending.length >= 256 * 1024) await output.writeFrom(pending.takeBytes());
    }
    if (output == null) return null;
    await output.writeFrom(pending.takeBytes());
    final header = pcmWavHeader(
      sampleRate: item.sampleRate,
      channels: item.channels,
      bitsPerSample: item.bitsPerSample,
      dataSize: dataSize,
    );
    await output.setPosition(0);
    await output.writeFrom(header);
    return outputPath;
  } finally {
    nativeDecoder?.destroy();
    await output?.close();
  }
}
