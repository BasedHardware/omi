import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/services.dart';

import 'package:omi/backend/http/api/tts.dart';

// Half a second at the endpoint's fixed 128 kbps output. This is enough MP3
// data for minimp3 to establish the stream geometry without waiting for the
// response body to finish.
const int progressiveTtsPrebufferBytes = 8 * 1024;
const Duration progressiveTtsStallTimeout = Duration(seconds: 15);

enum ProgressiveTtsTransferState { completed, failed, cancelled }

class ProgressiveTtsTransferResult {
  final ProgressiveTtsTransferState state;
  final Object? error;
  final StackTrace? stackTrace;

  const ProgressiveTtsTransferResult._(this.state, {this.error, this.stackTrace});

  const ProgressiveTtsTransferResult.completed() : this._(ProgressiveTtsTransferState.completed);

  const ProgressiveTtsTransferResult.cancelled() : this._(ProgressiveTtsTransferState.cancelled);

  const ProgressiveTtsTransferResult.failed(Object error, StackTrace stackTrace)
      : this._(ProgressiveTtsTransferState.failed, error: error, stackTrace: stackTrace);
}

class ProgressiveTtsStallException implements Exception {
  final Duration timeout;
  const ProgressiveTtsStallException(this.timeout);

  @override
  String toString() => 'TTS audio stream stalled for ${timeout.inSeconds}s';
}

/// Replays the bytes already received, then follows the live HTTP body.
///
/// The upstream subscription starts immediately, so later text chunks can be
/// prefetched while the current chunk plays. Cancellation tears down both the
/// HTTP request and every downstream reader.
class ProgressiveTtsAudioSource {
  final TtsAudioStream _upstream;
  final int prebufferBytes;
  final Duration stallTimeout;

  final List<Uint8List> _chunks = [];
  final List<StreamController<List<int>>> _readers = [];
  final Completer<void> _ready = Completer<void>();
  final Completer<ProgressiveTtsTransferResult> _settled = Completer<ProgressiveTtsTransferResult>();

  StreamSubscription<List<int>>? _subscription;
  Timer? _stallTimer;
  bool _closed = false;
  bool _cancelled = false;
  int _receivedBytes = 0;

  ProgressiveTtsAudioSource(
    this._upstream, {
    this.prebufferBytes = progressiveTtsPrebufferBytes,
    this.stallTimeout = progressiveTtsStallTimeout,
  }) {
    _start();
  }

  int get receivedBytes => _receivedBytes;
  int? get expectedBytes => _upstream.contentLength;
  Future<void> get ready => _ready.future;
  Future<ProgressiveTtsTransferResult> get settled => _settled.future;

  void _start() {
    _armStallTimer();
    _subscription = _upstream.bytes.listen(
      _onData,
      onError: (Object error, StackTrace stackTrace) {
        _finish(ProgressiveTtsTransferResult.failed(error, stackTrace));
        unawaited(_subscription?.cancel());
        unawaited(_upstream.cancel());
      },
      onDone: () => _finish(
        _cancelled ? const ProgressiveTtsTransferResult.cancelled() : const ProgressiveTtsTransferResult.completed(),
      ),
      cancelOnError: false,
    );
  }

  void _onData(List<int> bytes) {
    if (_closed || bytes.isEmpty) return;
    _armStallTimer();
    final chunk = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    _chunks.add(chunk);
    _receivedBytes += chunk.length;
    for (final reader in List<StreamController<List<int>>>.of(_readers)) {
      reader.add(chunk);
    }
    if (_receivedBytes >= prebufferBytes && !_ready.isCompleted) _ready.complete();
  }

  void _armStallTimer() {
    _stallTimer?.cancel();
    _stallTimer = Timer(stallTimeout, () async {
      if (_closed) return;
      final error = ProgressiveTtsStallException(stallTimeout);
      await _subscription?.cancel();
      await _upstream.cancel();
      _finish(ProgressiveTtsTransferResult.failed(error, StackTrace.current));
    });
  }

  void _finish(ProgressiveTtsTransferResult result) {
    if (_closed) return;
    _closed = true;
    _stallTimer?.cancel();
    if (!_ready.isCompleted) _ready.complete();
    for (final reader in List<StreamController<List<int>>>.of(_readers)) {
      reader.close();
    }
    _readers.clear();
    if (!_settled.isCompleted) _settled.complete(result);
  }

  Stream<List<int>> openRead() {
    late final StreamController<List<int>> controller;
    controller = StreamController<List<int>>(
      onListen: () {
        for (final chunk in _chunks) {
          controller.add(chunk);
        }
        if (_closed) {
          controller.close();
        } else {
          _readers.add(controller);
        }
      },
      onCancel: () => _readers.remove(controller),
    );
    return controller.stream;
  }

  Future<Uint8List> collectBytes() async {
    await settled;
    final builder = BytesBuilder(copy: false);
    for (final chunk in _chunks) {
      builder.add(chunk);
    }
    return builder.takeBytes();
  }

  Future<void> cancel() async {
    if (_closed) return;
    _cancelled = true;
    _stallTimer?.cancel();
    await _subscription?.cancel();
    await _upstream.cancel();
    _finish(const ProgressiveTtsTransferResult.cancelled());
  }
}

class ProgressiveTtsPlaybackResult {
  final bool started;
  final Duration position;
  final ProgressiveTtsTransferResult transfer;

  const ProgressiveTtsPlaybackResult({required this.started, required this.position, required this.transfer});
}

class _DecodedMp3Prefix {
  final Uint8List pcm;
  final int channels;
  final int sampleRate;

  const _DecodedMp3Prefix({required this.pcm, required this.channels, required this.sampleRate});
}

class _NativeMp3Decoder {
  static const _channel = MethodChannel('com.omi/tts_mp3_decoder');

  static Future<_DecodedMp3Prefix> decode(Uint8List bytes) async {
    final result = await _channel.invokeMapMethod<String, dynamic>('decode', {'bytes': bytes});
    final pcm = result?['pcm'];
    final channels = result?['channels'];
    final sampleRate = result?['sample_rate'];
    if (pcm is! Uint8List || channels is! int || sampleRate is! int) {
      throw const FormatException('Native MP3 decoder returned an invalid result');
    }
    return _DecodedMp3Prefix(pcm: pcm, channels: channels, sampleRate: sampleRate);
  }
}

/// Thin Dart owner for the app's AVAudioEngine / AudioTrack PCM stream.
class NativePcmStreamPlayer {
  static const _channel = MethodChannel('com.omi/tts_pcm_player');
  bool _started = false;
  bool _paused = false;

  bool get isPlaying => _started && !_paused;

  Future<void> open() async {}

  Future<void> start({required int channels, required int sampleRate}) async {
    await _channel.invokeMethod<void>('start', {'channels': channels, 'sample_rate': sampleRate});
    _started = true;
    _paused = false;
  }

  Future<void> feed(Uint8List bytes) async {
    if (!_started) return;
    await _channel.invokeMethod<void>('feed', {'pcm': bytes});
  }

  Future<void> pause() async {
    if (!_started || _paused) return;
    await _channel.invokeMethod<void>('pause');
    _paused = true;
  }

  Future<void> resume() async {
    if (!_started || !_paused) return;
    await _channel.invokeMethod<void>('resume');
    _paused = false;
  }

  Future<void> drain() async {
    if (!_started) return;
    await _channel.invokeMethod<void>('drain');
  }

  Future<void> stop() async {
    if (!_started) return;
    _started = false;
    _paused = false;
    await _channel.invokeMethod<void>('stop');
  }

  Future<void> close() => stop();
}

/// Decodes growing MP3 prefixes and feeds only newly available PCM samples to
/// the platform player. Re-decoding from the beginning makes frame boundaries
/// deterministic even when HTTP chunks split an MP3 frame.
class ProgressiveTtsPcmPlayer {
  final NativePcmStreamPlayer player;
  final int decodeStepBytes;

  ProgressiveTtsPcmPlayer(this.player, {this.decodeStepBytes = 32 * 1024});

  Future<ProgressiveTtsPlaybackResult> play(
    ProgressiveTtsAudioSource source, {
    void Function()? onStarted,
  }) async {
    await source.ready;
    if (source.receivedBytes == 0) {
      return ProgressiveTtsPlaybackResult(started: false, position: Duration.zero, transfer: await source.settled);
    }

    final compressed = BytesBuilder(copy: false);
    var lastDecodedAt = 0;
    var emittedBytes = 0;
    var channels = 0;
    var sampleRate = 0;
    var started = false;
    var decodedDuration = Duration.zero;
    var notifiedStarted = false;

    Future<void> decodeAvailable({required bool finalPass}) async {
      final bytes = compressed.toBytes();
      final threshold = emittedBytes == 0 ? progressiveTtsPrebufferBytes : decodeStepBytes;
      if (!finalPass && bytes.length - lastDecodedAt < threshold) return;
      lastDecodedAt = bytes.length;

      _DecodedMp3Prefix decoded;
      try {
        decoded = await _NativeMp3Decoder.decode(bytes);
      } on PlatformException catch (_) {
        if (!finalPass) return;
        rethrow;
      }
      if (decoded.pcm.length <= emittedBytes) return;
      if (channels != 0 && (decoded.channels != channels || decoded.sampleRate != sampleRate)) {
        throw StateError('TTS MP3 geometry changed during playback');
      }
      channels = decoded.channels;
      sampleRate = decoded.sampleRate;

      if (!started) {
        await player.start(channels: channels, sampleRate: sampleRate);
        started = true;
      }

      final delta = Uint8List.sublistView(decoded.pcm, emittedBytes);
      emittedBytes = decoded.pcm.length;
      decodedDuration = Duration(
        microseconds: emittedBytes * Duration.microsecondsPerSecond ~/ 2 ~/ channels ~/ sampleRate,
      );
      await player.feed(delta);
      if (!notifiedStarted) {
        notifiedStarted = true;
        onStarted?.call();
      }
    }

    try {
      await for (final bytes in source.openRead()) {
        compressed.add(bytes);
        await decodeAvailable(finalPass: false);
      }
      if (compressed.length > 0) await decodeAvailable(finalPass: true);

      final transfer = await source.settled;
      if (started) {
        await player.drain();
        await player.stop();
      }
      return ProgressiveTtsPlaybackResult(started: started, position: decodedDuration, transfer: transfer);
    } catch (error, stackTrace) {
      // Preserve the same partial-playback contract for decoder/output failures
      // as for transport failures. The caller can then fall back with only the
      // untouched text instead of repeating audio the user already heard.
      if (started) {
        await player.drain();
        await player.stop();
      }
      return ProgressiveTtsPlaybackResult(
        started: started,
        position: decodedDuration,
        transfer: ProgressiveTtsTransferResult.failed(error, stackTrace),
      );
    }
  }
}
