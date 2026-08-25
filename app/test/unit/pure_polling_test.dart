import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/services/sockets/pure_polling.dart';
import 'package:omi/services/sockets/pure_socket.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed transcribe keeps the audio buffered and does not tear the socket down', () async {
    final provider = _FakeSttProvider();
    provider.enqueueError(Exception('connection refused'));
    provider.enqueueSuccess(SttTranscriptionResult(segments: [SttSegment(text: 'hi', start: 0, end: 1)]));

    final socket = PurePollingSocket(config: const AudioPollingConfig(minBufferSizeBytes: 1), sttProvider: provider);
    final listener = _FakeListener();
    socket.setListener(listener);

    expect(await socket.connect(), isTrue);

    socket.send(Uint8List.fromList([1, 2, 3]));
    await socket.flushNow();

    // The failed attempt must not be reported as a fatal socket error/close —
    // that used to tear down the whole composite (including the healthy
    // secondary/raw-audio socket) on every transient STT hiccup.
    expect(listener.errors, isEmpty);
    expect(listener.closes, isEmpty);
    expect(socket.status, PureSocketStatus.connected);
    expect(socket.isBuffering, isTrue);
    expect(socket.bufferingSince, isNotNull);

    // More audio arrives while still "offline".
    socket.send(Uint8List.fromList([4, 5, 6]));
    await socket.flushNow();

    // The retry call must have seen both the requeued and the newly
    // captured audio — nothing was dropped while offline.
    expect(provider.receivedCalls.last, [1, 2, 3, 4, 5, 6]);
    expect(listener.messages, hasLength(1));
    expect(socket.isBuffering, isFalse);
    expect(socket.bufferingSince, isNull);
  });

  test('keeps retrying on every subsequent flush while the endpoint stays down', () async {
    final provider = _FakeSttProvider()..alwaysThrow(Exception('still down'));

    final socket = PurePollingSocket(config: const AudioPollingConfig(minBufferSizeBytes: 1), sttProvider: provider);
    socket.setListener(_FakeListener());
    await socket.connect();

    socket.send(Uint8List.fromList([1]));
    await socket.flushNow();
    socket.send(Uint8List.fromList([2]));
    await socket.flushNow();
    socket.send(Uint8List.fromList([3]));
    await socket.flushNow();

    expect(provider.receivedCalls, [
      [1],
      [1, 2],
      [1, 2, 3],
    ]);
    expect(socket.bufferedBytes, 3);
  });

  test('trims the oldest buffered audio once past the configured cap', () async {
    final provider = _FakeSttProvider()..alwaysThrow(Exception('still down'));

    final socket = PurePollingSocket(
      config: const AudioPollingConfig(minBufferSizeBytes: 1, maxBufferBytes: 5),
      sttProvider: provider,
    );
    socket.setListener(_FakeListener());
    await socket.connect();

    for (final byte in [1, 2, 3, 4, 5, 6, 7]) {
      socket.send(Uint8List.fromList([byte]));
      await socket.flushNow();
    }

    expect(socket.bufferedBytes, lessThanOrEqualTo(5));
    // Newest audio survives; oldest was dropped.
    expect(provider.receivedCalls.last.last, 7);
  });
}

class _FakeSttProvider implements ISttProvider {
  final List<List<int>> receivedCalls = [];
  final _behaviors = <Future<SttTranscriptionResult?> Function()>[];
  Future<SttTranscriptionResult?> Function()? _default;

  void enqueueError(Object error) => _behaviors.add(() => Future<SttTranscriptionResult?>.error(error));
  void enqueueSuccess(SttTranscriptionResult result) => _behaviors.add(() async => result);
  void alwaysThrow(Object error) => _default = () => Future<SttTranscriptionResult?>.error(error);

  @override
  Future<SttTranscriptionResult?> transcribe(Uint8List audioData, {double audioOffsetSeconds = 0}) {
    receivedCalls.add(audioData.toList());
    final behavior = _behaviors.isNotEmpty ? _behaviors.removeAt(0) : (_default ?? () async => null);
    return behavior();
  }

  @override
  void dispose() {}
}

class _FakeListener implements IPureSocketListener {
  final List<Object> errors = [];
  final List<int?> closes = [];
  final List<dynamic> messages = [];
  int connects = 0;

  @override
  void onConnected() => connects++;

  @override
  void onMessage(dynamic message) => messages.add(message);

  @override
  void onClosed([int? closeCode]) => closes.add(closeCode);

  @override
  void onError(Object err, StackTrace trace) => errors.add(err);
}
