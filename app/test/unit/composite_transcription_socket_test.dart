import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

void main() {
  // The service-level tests attach listen client state, which reads WidgetsBinding.
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_TestEnvFields());
  });

  group('CompositeTranscriptionSocket raw audio forwarding', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('does not send input frames to the Omi socket when disabled', () async {
      final primary = _FakeSocket();
      final secondary = _FakeSocket();
      final socket = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        forwardRawAudioToSecondary: false,
      );

      expect(await socket.connect(), isTrue);
      final audio = Uint8List.fromList([1, 2, 3]);
      socket.send(audio);

      expect(primary.sent, [same(audio)]);
      expect(secondary.sent, isEmpty);
    });

    test('still forwards primary transcripts to Omi when input forwarding is disabled', () async {
      final primary = _FakeSocket();
      final secondary = _FakeSocket();
      final socket = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        forwardRawAudioToSecondary: false,
        sttProvider: 'customLive',
      );

      expect(await socket.connect(), isTrue);
      primary.emitMessage(
        jsonEncode([
          {'text': 'private audio, shared transcript'},
        ]),
      );

      expect(secondary.sent, hasLength(1));
      expect(jsonDecode(secondary.sent.single as String), {
        'type': 'suggested_transcript',
        'segments': [
          {'text': 'private audio, shared transcript'},
        ],
        'stt_provider': 'customLive',
      });
    });

    test('keeps forwarding non-audio control messages to Omi when audio forwarding is disabled', () async {
      final primary = _FakeSocket();
      final secondary = _FakeSocket();
      final socket = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        forwardRawAudioToSecondary: false,
      );

      expect(await socket.connect(), isTrue);
      final controlMessage = jsonEncode({'type': 'speaker_assigned', 'speaker_id': 1});
      socket.send(controlMessage);

      expect(primary.sent, [controlMessage]);
      expect(secondary.sent, [controlMessage]);
    });

    test('keeps forwarding input frames by default', () async {
      final primary = _FakeSocket();
      final secondary = _FakeSocket();
      final socket = CompositeTranscriptionSocket(primarySocket: primary, secondarySocket: secondary);

      expect(await socket.connect(), isTrue);
      final audio = Uint8List.fromList([4, 5, 6]);
      socket.send(audio);

      expect(primary.sent, [same(audio)]);
      expect(secondary.sent, [same(audio)]);
    });

    test('freemium on-device composite stays unnamed and does not forward audio', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        identity: 'freemium:on-device',
        sendRawAudioToOmi: false,
      );

      expect(TranscriptSocketServiceFactory.includeSpeechProfileForCustomSecondary(config.sttConfigId), isFalse);

      final service = TranscriptSocketServiceFactory.createFromCustomConfig(16000, BleAudioCodec.pcm16, 'en', config);

      expect(service.socket, isA<CompositeTranscriptionSocket>());
      expect((service.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isFalse);
    });

    test('user custom STT still requests a speech profile on the Omi secondary', () {
      expect(
        TranscriptSocketServiceFactory.includeSpeechProfileForCustomSecondary('custom:deepgram'),
        isTrue,
      );
    });

    test('factory applies the persisted forwarding setting', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        sendRawAudioToOmi: false,
      );

      final service = TranscriptSocketServiceFactory.createFromCustomConfig(16000, BleAudioCodec.pcm16, 'en', config);

      expect(service.socket, isA<CompositeTranscriptionSocket>());
      expect((service.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isFalse);
    });

    test('speech-profile on-device fallback honors the raw-audio setting too', () {
      // A local-only config must not leak raw audio to the Omi secondary in
      // the speech-profile flow either; suggested transcripts still flow.
      const config = CustomSttConfig(
        provider: SttProvider.custom,
        url: 'https://stt.example.test/poll',
        requestType: SttRequestType.multipartForm,
        sendRawAudioToOmi: false,
      );

      final service = TranscriptSocketServiceFactory.createSpeechProfileOnDevice(
        16000,
        BleAudioCodec.pcm16,
        'en',
        config,
      );

      expect(service.socket, isA<CompositeTranscriptionSocket>());
      expect((service.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isFalse);
    });

    test('blocks unsupported-codec Omi fallback when raw audio forwarding is disabled', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        sendRawAudioToOmi: false,
      );

      expect(
        TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(BleAudioCodec.lc3FS1030, config),
        isTrue,
      );
    });

    test('allows unsupported-codec Omi fallback only when raw audio forwarding is enabled', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        sendRawAudioToOmi: true,
      );

      expect(
        TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(BleAudioCodec.lc3FS1030, config),
        isFalse,
      );
    });

    test('does not block a supported custom STT codec', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        sendRawAudioToOmi: false,
      );

      expect(TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(BleAudioCodec.pcm16, config), isFalse);
    });
  });

  group('CompositeTranscriptionSocket when the Omi socket fails', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    CompositeTranscriptionSocket build(
      _ScriptedSocket primary,
      _ScriptedSocket secondary, {
      bool keepPrimary = true,
    }) {
      return CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        keepPrimaryWhenSecondaryFails: keepPrimary,
        secondaryRetryInitialDelay: const Duration(milliseconds: 10),
        secondaryRetryMaxDelay: const Duration(milliseconds: 40),
      );
    }

    test('default behaviour is unchanged: a failed Omi connect fails the composite', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false]);
      // Default constructor: keepPrimaryWhenSecondaryFails is not passed.
      final socket = CompositeTranscriptionSocket(primarySocket: primary, secondarySocket: secondary);

      expect(socket.keepPrimaryWhenSecondaryFails, isFalse);

      expect(await socket.connect(), isFalse);
      expect(socket.status, PureSocketStatus.notConnected);
      expect(primary.status, PureSocketStatus.disconnected);
    });

    test('a failed Omi connect keeps the custom STT socket live and degraded', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, false, false, false, false]);
      final listener = _RecordingListener();
      final socket = build(primary, secondary)..setListener(listener);

      expect(await socket.connect(), isTrue);
      expect(socket.status, PureSocketStatus.connected);
      expect(socket.secondaryDegraded, isTrue);
      expect(listener.connected, 1);

      final audio = Uint8List.fromList([7, 8, 9]);
      socket.send(audio);
      expect(primary.sent, [same(audio)]);
      expect(secondary.sent, isEmpty);

      primary.emitMessage(jsonEncode([
        {'text': 'turn on the lights'},
      ]));
      expect(secondary.sent, isEmpty, reason: 'transcripts cannot reach Omi while degraded');
      await socket.stop();
    });

    test('an Omi socket that drops mid-session does not tear down the composite', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [true, false, false, false, false, false]);
      final listener = _RecordingListener();
      final socket = build(primary, secondary)..setListener(listener);

      expect(await socket.connect(), isTrue);
      expect(socket.secondaryDegraded, isFalse);

      secondary.emitClosed(1011);
      expect(socket.status, PureSocketStatus.connected);
      expect(socket.secondaryDegraded, isTrue);
      expect(listener.closed, isEmpty);
      expect(primary.status, PureSocketStatus.connected);
      await socket.stop();
    });

    test('the custom STT socket closing still tears everything down', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket();
      final listener = _RecordingListener();
      final socket = build(primary, secondary)..setListener(listener);

      expect(await socket.connect(), isTrue);
      primary.emitClosed(1001);
      expect(socket.status, PureSocketStatus.disconnected);
      expect(listener.closed, [1001]);
    });

    test('the Omi socket is retried in the background and restored', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, false, true]);
      final socket = build(primary, secondary);

      expect(await socket.connect(), isTrue);
      expect(socket.secondaryDegraded, isTrue);

      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(secondary.connectCalls, 3);
      expect(socket.secondaryDegraded, isFalse);

      final audio = Uint8List.fromList([1]);
      socket.send(audio);
      expect(secondary.sent, [same(audio)]);
      await socket.stop();
    });

    test('stopping the composite cancels Omi retries', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, true]);
      final socket = build(primary, secondary);

      expect(await socket.connect(), isTrue);
      await socket.stop();
      await Future<void>.delayed(const Duration(milliseconds: 60));

      expect(secondary.connectCalls, 1);
      expect(socket.secondaryDegraded, isFalse);
    });

    test('the service reports no delivery to Omi while degraded with raw-audio forwarding', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, false, false, false, false]);
      final service =
          TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', build(primary, secondary));

      expect(service.deliversToOmi, isTrue, reason: 'nothing degraded before connecting');
      await service.start();
      expect(service.state, SocketServiceState.connected);
      expect(service.deliversToOmi, isFalse);
      await service.stop();
    });

    test('raw-audio opt-out keeps marking frames synced while degraded (no later upload)', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, false, false, false, false]);
      final composite = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
        forwardRawAudioToSecondary: false,
        keepPrimaryWhenSecondaryFails: true,
        secondaryRetryInitialDelay: const Duration(milliseconds: 10),
        secondaryRetryMaxDelay: const Duration(milliseconds: 40),
      );
      final service = TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', composite);

      await service.start();
      expect(composite.secondaryDegraded, isTrue);
      expect(service.deliversToOmi, isTrue);
      await service.stop();
    });

    test('a primary close clears degraded state so a reconnect retries Omi again', () async {
      final primary = _ScriptedSocket();
      final secondary = _ScriptedSocket(connectResults: [false, false, false, false, false, false, false, true]);
      final socket = build(primary, secondary);

      expect(await socket.connect(), isTrue);
      expect(socket.secondaryDegraded, isTrue);

      primary.emitClosed(1006);
      expect(socket.status, PureSocketStatus.disconnected);
      expect(socket.secondaryDegraded, isFalse);
      final callsAfterClose = secondary.connectCalls;
      await Future<void>.delayed(const Duration(milliseconds: 60));
      expect(secondary.connectCalls, callsAfterClose, reason: 'no retries after the primary closed');

      expect(await socket.connect(), isTrue);
      expect(socket.secondaryDegraded, isTrue);
      await Future<void>.delayed(const Duration(milliseconds: 400));
      expect(socket.secondaryDegraded, isFalse, reason: 'retry loop runs again on the reconnected composite');
      await socket.stop();
    });

    test('live custom STT turns degraded mode on and reports delivery to Omi', () async {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
      );
      final service = TranscriptSocketServiceFactory.createFromCustomConfig(16000, BleAudioCodec.pcm16, 'en', config);
      final composite = service.socket as CompositeTranscriptionSocket;

      expect(composite.keepPrimaryWhenSecondaryFails, isTrue);
      expect(service.deliversToOmi, isTrue);
    });
  });
}

class _RecordingListener implements IPureSocketListener {
  int connected = 0;
  final List<int?> closed = [];

  @override
  void onConnected() => connected++;

  @override
  void onMessage(dynamic message) {}

  @override
  void onClosed([int? closeCode]) => closed.add(closeCode);

  @override
  void onError(Object err, StackTrace trace) {}
}

/// Fake socket whose successive connect() calls return [connectResults]
/// (true once the list is exhausted).
class _ScriptedSocket implements IPureSocket {
  _ScriptedSocket({List<bool>? connectResults}) : _connectResults = [...?connectResults];

  final List<bool> _connectResults;
  final List<dynamic> sent = [];
  int connectCalls = 0;
  IPureSocketListener? _listener;
  PureSocketStatus _status = PureSocketStatus.notConnected;

  @override
  PureSocketStatus get status => _status;

  @override
  Future<bool> connect() async {
    connectCalls++;
    final ok = _connectResults.isEmpty ? true : _connectResults.removeAt(0);
    _status = ok ? PureSocketStatus.connected : PureSocketStatus.notConnected;
    if (ok) _listener?.onConnected();
    return ok;
  }

  @override
  Future<void> disconnect() async {
    _status = PureSocketStatus.disconnected;
  }

  @override
  Future<void> stop() => disconnect();

  @override
  void send(dynamic message) => sent.add(message);

  @override
  void setListener(IPureSocketListener listener) => _listener = listener;

  @override
  void onClosed() => _listener?.onClosed();

  @override
  void onConnected() => _listener?.onConnected();

  @override
  void onError(Object err, StackTrace trace) => _listener?.onError(err, trace);

  @override
  void onMessage(dynamic message) => _listener?.onMessage(message);

  void emitMessage(dynamic message) => _listener?.onMessage(message);

  void emitClosed([int? code]) {
    _status = PureSocketStatus.disconnected;
    _listener?.onClosed(code);
  }
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.example.test/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

class _FakeSocket implements IPureSocket {
  final List<dynamic> sent = [];
  IPureSocketListener? _listener;
  PureSocketStatus _status = PureSocketStatus.notConnected;

  @override
  PureSocketStatus get status => _status;

  @override
  Future<bool> connect() async {
    _status = PureSocketStatus.connected;
    _listener?.onConnected();
    return true;
  }

  @override
  Future<void> disconnect() async {
    _status = PureSocketStatus.disconnected;
  }

  @override
  void onClosed() => _listener?.onClosed();

  @override
  void onConnected() => _listener?.onConnected();

  @override
  void onError(Object err, StackTrace trace) => _listener?.onError(err, trace);

  @override
  void onMessage(dynamic message) => _listener?.onMessage(message);

  @override
  void send(dynamic message) => sent.add(message);

  @override
  void setListener(IPureSocketListener listener) => _listener = listener;

  @override
  Future<void> stop() => disconnect();

  void emitMessage(dynamic message) => _listener?.onMessage(message);
}
