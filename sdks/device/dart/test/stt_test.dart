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

    expect(channel.events, ['send', 'close']);
    expect(channel.sent, [jsonEncode({'type': 'CloseStream'})]);
    expect(channel.closed, isTrue);
  });

  test('Deepgram stop still closes when CloseStream send fails', () async {
    final channel = RecordingWebSocketChannel(sendError: StateError('synthetic send failure'));
    final transcriber = DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: (_) {},
      channel: channel,
    );

    await transcriber.stop();

    expect(channel.events, ['send', 'close']);
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

  test('Deepgram stop drains a trailing transcript after CloseStream', () async {
    final channel = RecordingWebSocketChannel(
      trailingAfterCloseStream: jsonEncode({
        'channel': {
          'alternatives': [
            {'transcript': 'final dart'},
          ],
        },
      }),
    );
    final transcripts = <String>[];
    final transcriber = DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: transcripts.add,
      channel: channel,
    );

    await transcriber.stop();

    expect(transcripts, ['final dart']);
    expect(channel.events, ['send', 'close']);
  });

  test('Deepgram stop still closes if the provider never drains', () async {
    final channel = RecordingWebSocketChannel(completeStreamOnCloseStream: false);
    final transcriber = DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: (_) {},
      channel: channel,
      drainTimeout: const Duration(milliseconds: 50),
    );

    await transcriber.stop();

    expect(channel.events, ['send', 'close']);
    expect(channel.closed, isTrue);
  });

  test('Parakeet stop sends finalize before closing the socket', () async {
    final channel = RecordingWebSocketChannel();
    final transcriber = ParakeetTranscriber(
      apiUrl: 'https://parakeet.example',
      onTranscript: (_) {},
      channel: channel,
    );

    await transcriber.stop();

    expect(channel.events, ['send', 'close']);
    expect(channel.sent, ['finalize']);
    expect(channel.closed, isTrue);
  });

  test('Parakeet stop still closes when finalize send fails', () async {
    final channel = RecordingWebSocketChannel(sendError: StateError('synthetic send failure'));
    final transcriber = ParakeetTranscriber(
      apiUrl: 'https://parakeet.example',
      onTranscript: (_) {},
      channel: channel,
    );

    await transcriber.stop();

    expect(channel.events, ['send', 'close']);
    expect(channel.closed, isTrue);
  });

  test('Parakeet stop drains a trailing transcript after finalize', () async {
    final channel = RecordingWebSocketChannel(
      trailingAfterCloseStream: jsonEncode({'text': 'final para'}),
    );
    final transcripts = <String>[];
    final transcriber = ParakeetTranscriber(
      apiUrl: 'https://parakeet.example',
      onTranscript: transcripts.add,
      channel: channel,
    );

    await transcriber.stop();

    expect(transcripts, ['final para']);
    expect(channel.events, ['send', 'close']);
  });

  test('Parakeet stop still closes if the provider never drains', () async {
    final channel = RecordingWebSocketChannel(completeStreamOnCloseStream: false);
    final transcriber = ParakeetTranscriber(
      apiUrl: 'https://parakeet.example',
      onTranscript: (_) {},
      channel: channel,
      drainTimeout: const Duration(milliseconds: 50),
    );

    await transcriber.stop();

    expect(channel.events, ['send', 'close']);
    expect(channel.closed, isTrue);
  });

  test('Parakeet rejects PCM and a second finalize while draining', () async {
    final channel = RecordingWebSocketChannel(completeStreamOnCloseStream: false);
    final transcriber = ParakeetTranscriber(
      apiUrl: 'https://parakeet.example',
      onTranscript: (_) {},
      channel: channel,
      drainTimeout: const Duration(milliseconds: 50),
    );
    channel.addIncoming(jsonEncode({'type': 'ready'}));
    await Future<void>.delayed(Duration.zero);

    transcriber.appendPcm(Uint8List.fromList([1, 2]));
    final stop = transcriber.stop();
    await Future<void>.delayed(Duration.zero);
    transcriber.appendPcm(Uint8List.fromList([3, 4]));
    await transcriber.stop();
    await stop;

    expect(channel.sent, [Uint8List.fromList([1, 2]), 'finalize']);
  });

  test('Deepgram rejects PCM and a second CloseStream while draining', () async {
    final channel = RecordingWebSocketChannel(completeStreamOnCloseStream: false);
    final transcriber = DeepgramTranscriber(
      apiKey: 'fake-key',
      onTranscript: (_) {},
      channel: channel,
      drainTimeout: const Duration(milliseconds: 50),
    );

    transcriber.appendPcm(Uint8List.fromList([1, 2]));
    final stop = transcriber.stop();
    await Future<void>.delayed(Duration.zero);
    transcriber.appendPcm(Uint8List.fromList([3, 4]));
    await transcriber.stop();
    await stop;

    expect(channel.sent, [Uint8List.fromList([1, 2]), jsonEncode({'type': 'CloseStream'})]);
  });
}

class RecordingWebSocketChannel extends StreamChannelMixin implements WebSocketChannel {
  RecordingWebSocketChannel({
    this.sendError,
    this.trailingAfterCloseStream,
    this.completeStreamOnCloseStream = true,
  });

  final Object? sendError;
  final Object? trailingAfterCloseStream;
  final bool completeStreamOnCloseStream;
  final sent = <Object?>[];
  final events = <String>[];
  bool closed = false;
  final _incoming = StreamController<Object?>.broadcast();

  void addIncoming(Object? event) => _incoming.add(event);

  void closeIncoming() {
    if (!_incoming.isClosed) {
      _incoming.close();
    }
  }

  @override
  late final WebSocketSink sink = _RecordingSink(this);

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
  void add(Object? event) {
    _parent.events.add('send');
    _parent.sent.add(event);
    final error = _parent.sendError;
    if (error != null) {
      throw error;
    }
    if ((event == jsonEncode({'type': 'CloseStream'}) || event == 'finalize') &&
        _parent.completeStreamOnCloseStream) {
      scheduleMicrotask(() {
        final trailing = _parent.trailingAfterCloseStream;
        if (trailing != null) {
          _parent.addIncoming(trailing);
        }
        _parent.closeIncoming();
      });
    }
  }

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
    _parent.events.add('close');
    _parent.closed = true;
    _parent.closeCode = closeCode;
    _parent.closeReason = closeReason;
    if (!_done.isCompleted) _done.complete();
  }

  @override
  Future get done => _done.future;
}
