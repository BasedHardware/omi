import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/sockets/composite_transcription_socket.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

void main() {
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
      primary.emitMessage(jsonEncode([
        {'text': 'private audio, shared transcript'}
      ]));

      expect(secondary.sent, hasLength(1));
      expect(jsonDecode(secondary.sent.single as String), {
        'type': 'suggested_transcript',
        'segments': [
          {'text': 'private audio, shared transcript'}
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
      final socket = CompositeTranscriptionSocket(
        primarySocket: primary,
        secondarySocket: secondary,
      );

      expect(await socket.connect(), isTrue);
      final audio = Uint8List.fromList([4, 5, 6]);
      socket.send(audio);

      expect(primary.sent, [same(audio)]);
      expect(secondary.sent, [same(audio)]);
    });

    test('factory applies the persisted forwarding setting', () {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        sendRawAudioToOmi: false,
      );

      final service = TranscriptSocketServiceFactory.createFromCustomConfig(
        16000,
        BleAudioCodec.pcm16,
        'en',
        config,
      );

      expect(service.socket, isA<CompositeTranscriptionSocket>());
      expect((service.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isFalse);
    });
  });
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.example.test/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get googleMapsApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get openAIAPIKey => null;

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
