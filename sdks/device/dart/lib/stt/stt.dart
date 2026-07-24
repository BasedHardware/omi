import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

enum SttEngine { deepgram, whisper, parakeet }

typedef TranscriptHandler = void Function(String text);

abstract class StreamingTranscriber {
  void appendPcm(Uint8List chunk);
  Future<void> stop();
}

String deepgramWsUrl({int sampleRate = 16000}) {
  return 'wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US'
      '&encoding=linear16&sample_rate=$sampleRate&channels=1';
}

String parakeetWsUrl(String apiUrl, {int sampleRate = 16000}) {
  var base = apiUrl.trim();
  while (base.endsWith('/')) {
    base = base.substring(0, base.length - 1);
  }
  base = base.replaceFirst(RegExp(r'^https:'), 'wss:');
  base = base.replaceFirst(RegExp(r'^http:'), 'ws:');
  return '$base/v3/stream?sample_rate=$sampleRate';
}

class DeepgramTranscriber implements StreamingTranscriber {
  DeepgramTranscriber({required this.apiKey, required this.onTranscript, this.sampleRate = 16000}) {
    final uri = Uri.parse(deepgramWsUrl(sampleRate: sampleRate));
    _channel = IOWebSocketChannel.connect(uri, headers: {'Authorization': 'Token $apiKey'});
    _sub = _channel.stream.listen((event) {
      if (event is! String) return;
      try {
        final data = jsonDecode(event) as Map<String, dynamic>;
        final alts = (data['channel'] as Map?)?['alternatives'] as List?;
        final t = (alts?.isNotEmpty == true) ? (alts!.first as Map)['transcript'] : null;
        if (t is String && t.isNotEmpty) onTranscript(t);
      } catch (_) {}
    });
  }

  final String apiKey;
  final TranscriptHandler onTranscript;
  final int sampleRate;
  late final WebSocketChannel _channel;
  StreamSubscription? _sub;

  @override
  void appendPcm(Uint8List chunk) {
    _channel.sink.add(chunk);
  }

  @override
  Future<void> stop() async {
    await _sub?.cancel();
    await _channel.sink.close();
  }
}

class ParakeetTranscriber implements StreamingTranscriber {
  ParakeetTranscriber({required String apiUrl, required this.onTranscript, this.sampleRate = 16000}) {
    final uri = Uri.parse(parakeetWsUrl(apiUrl, sampleRate: sampleRate));
    _channel = WebSocketChannel.connect(uri);
    _sub = _channel.stream.listen((event) {
      if (event is! String) return;
      try {
        final data = jsonDecode(event) as Map<String, dynamic>;
        if (data['type'] == 'ready') {
          _ready = true;
          return;
        }
        final text = _extract(data);
        if (text != null && text.isNotEmpty) onTranscript(text);
      } catch (_) {}
    });
  }

  final TranscriptHandler onTranscript;
  final int sampleRate;
  late final WebSocketChannel _channel;
  StreamSubscription? _sub;
  bool _ready = false;

  static String? _extract(Map<String, dynamic> data) {
    final t = data['text'] ?? data['transcript'];
    if (t is String && t.isNotEmpty) return t;
    return null;
  }

  @override
  void appendPcm(Uint8List chunk) {
    if (_ready) _channel.sink.add(chunk);
  }

  @override
  Future<void> stop() async {
    try {
      _channel.sink.add('finalize');
    } catch (_) {}
    await _sub?.cancel();
    await _channel.sink.close();
  }
}

/// Feature-gated Whisper via injected runner.
class WhisperTranscriber implements StreamingTranscriber {
  WhisperTranscriber({required this.runner, required this.onTranscript, this.batchSeconds = 5});

  final FutureOr<String> Function(Uint8List pcm) runner;
  final TranscriptHandler onTranscript;
  final int batchSeconds;
  final BytesBuilder _buf = BytesBuilder(copy: false);
  bool _stopped = false;

  @override
  void appendPcm(Uint8List chunk) {
    if (_stopped) return;
    _buf.add(chunk);
    final target = batchSeconds * 16000 * 2;
    if (_buf.length >= target) {
      unawaited(_flush());
    }
  }

  Future<void> _flush() async {
    final pcm = Uint8List.fromList(_buf.takeBytes());
    if (pcm.isEmpty) return;
    final text = await runner(pcm);
    if (!_stopped && text.isNotEmpty) onTranscript(text);
  }

  @override
  Future<void> stop() async {
    _stopped = true;
    await _flush();
  }
}

StreamingTranscriber createTranscriber({
  required SttEngine engine,
  required TranscriptHandler onTranscript,
  String? apiKey,
  String? apiUrl,
  FutureOr<String> Function(Uint8List pcm)? whisperRunner,
  int sampleRate = 16000,
}) {
  switch (engine) {
    case SttEngine.deepgram:
      if (apiKey == null || apiKey.isEmpty) {
        throw ArgumentError('Deepgram apiKey required');
      }
      return DeepgramTranscriber(apiKey: apiKey, onTranscript: onTranscript, sampleRate: sampleRate);
    case SttEngine.parakeet:
      if (apiUrl == null || apiUrl.isEmpty) {
        throw ArgumentError('Parakeet apiUrl required');
      }
      return ParakeetTranscriber(apiUrl: apiUrl, onTranscript: onTranscript, sampleRate: sampleRate);
    case SttEngine.whisper:
      if (whisperRunner == null) {
        throw ArgumentError('Whisper requires whisperRunner');
      }
      return WhisperTranscriber(runner: whisperRunner!, onTranscript: onTranscript);
  }
}
