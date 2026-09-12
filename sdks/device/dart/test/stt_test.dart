import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_device/omi_device.dart';
import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

void main() {
  test('deepgramWsUrl omits api key from query string', () {
    expect(
      deepgramWsUrl(),
      'wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1',
    );
    expect(deepgramWsUrl(sampleRate: 8000), contains('sample_rate=8000'));
    expect(deepgramWsUrl(), isNot(contains('token=')));
  });

  test('parakeetWsUrl', () {
    expect(parakeetWsUrl('https://parakeet.example/'), 'wss://parakeet.example/v3/stream?sample_rate=16000');
  });

  test('whisper requires runner', () {
    expect(() => createTranscriber(engine: SttEngine.whisper, onTranscript: (_) {}), throwsA(isA<ArgumentError>()));
  });

  test('whisper stop delivers buffered audio transcript before the batch fills', () async {
    final transcripts = <String>[];
    final transcriber = createTranscriber(
      engine: SttEngine.whisper,
      onTranscript: transcripts.add,
      whisperRunner: (_) => 'final transcript',
    );

    transcriber.appendPcm(Uint8List.fromList([1, 2, 3]));
    await transcriber.stop();

    expect(transcripts, ['final transcript']);
  });

  test('Deepgram stop sends CloseStream before closing the socket', () async {
    final channel = RecordingWebSocketChannel();
    final transcriber = DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: (_) {},
      channel: channel,
    );

    await transcriber.stop();

    expect(channel.sent, [jsonEncode({'type': 'CloseStream'})]);
    expect(channel.closed, isTrue);
  });

  test('Deepgram still delivers transcripts until stop', () async {
    final channel = RecordingWebSocketChannel();
    final transcripts = <String>[];
    DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: transcripts.add,
      channel: channel,
    );

    channel.addIncoming(
      jsonEncode({
        'channel': {
          'alternatives': [
            {'transcript': 'hello dart'},
          ],
        },
      }),
    );
    await Future<void>.delayed(Duration.zero);

    expect(transcripts, ['hello dart']);
  });
}

class RecordingWebSocketChannel extends StreamChannelMixin implements WebSocketChannel {
  RecordingWebSocketChannel() {
    sink = _RecordingSink(this);
  }

  final sent = <Object?>[];
  bool closed = false;
  final _incoming = StreamController<Object?>.broadcast();

  void addIncoming(Object? event) => _incoming.add(event);

  @override
  late final WebSocketSink sink;

  @override
  Stream get stream => _incoming.stream;

  @override
  Future<void> get ready => Future<void>.value();

  @override
  String? protocol;

  @override
  int? closeCode;

  @override
  String? closeReason;
}

class _RecordingSink implements WebSocketSink {
  _RecordingSink(this._parent);

  final RecordingWebSocketChannel _parent;
  final _done = Completer<void>();

  @override
  void add(Object? event) => _parent.sent.add(event);

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future addStream(Stream stream) async {
    await for (final event in stream) {
      add(event);
    }
  }

  @override
  Future close([int? closeCode, String? closeReason]) async {
    _parent.closed = true;
    _parent.closeCode = closeCode;
    _parent.closeReason = closeReason;
    if (!_done.isCompleted) _done.complete();
  }

  @override
  Future get done => _done.future;
}
