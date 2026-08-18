import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/sockets.dart';
import 'package:omi/services/sockets/local_only_transcription_socket.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/mutex.dart';

void main() {
  setUpAll(() {
    Env.init(_TestEnvFields());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('LocalOnlyTranscriptionSocket', () {
    test('delegates transport operations to the primary only', () async {
      final primary = _FakeSocket();
      final socket = LocalOnlyTranscriptionSocket(primarySocket: primary);

      expect(socket, isNot(isA<CompositeTranscriptionSocket>()));
      expect(socket.status, PureSocketStatus.notConnected);
      expect(await socket.connect(), isTrue);
      expect(primary.connectCalls, 1);

      socket.send('ping');
      expect(primary.sent, ['ping']);

      await socket.disconnect();
      await socket.stop();
      expect(primary.disconnectCalls, 2);
      expect(primary.stopCalls, 1);
    });

    test('makes primary transcript segments observable by the existing service listener', () async {
      final primary = _FakeSocket();
      final localOnlySocket = LocalOnlyTranscriptionSocket(primarySocket: primary);
      final service = TranscriptSegmentSocketService.withSocket(
        16000,
        BleAudioCodec.pcm16,
        'en',
        localOnlySocket,
        customSttMode: true,
      );

      final receivedSegments = <TranscriptSegment>[];
      service.subscribe('local-only-test', _RecordingListener(onSegments: receivedSegments.addAll));

      await localOnlySocket.connect();
      primary.emitMessage(
        jsonEncode([
          {
            'id': 's1',
            'text': 'hello from the primary',
            'speaker': 'SPEAKER_00',
            'is_user': false,
            'start': 0.0,
            'end': 1.0,
          },
        ]),
      );

      expect(receivedSegments, hasLength(1));
      expect(receivedSegments.single.text, 'hello from the primary');
    });

    test('forwards primary lifecycle events without a secondary listener', () {
      final primary = _FakeSocket();
      final socket = LocalOnlyTranscriptionSocket(primarySocket: primary);
      final listener = _RecordingPureSocketListener();
      socket.setListener(listener);

      primary.emitConnected();
      primary.emitClosed(1000);
      final error = Exception('primary failed');
      primary.emitError(error);

      expect(listener.connectedCount, 1);
      expect(listener.closedCodes, [1000]);
      expect(listener.errors, [error]);
    });
  });

  group('TranscriptSocketServiceFactory privacy policy branches', () {
    test('localOnly starts the primary, exposes its transcript, and skips the Omi factory', () async {
      const config = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        privacyPolicy: SttPrivacyPolicy.localOnly,
      );
      final primary = _FakeSocket();
      var secondaryFactoryCalls = 0;

      final service = TranscriptSocketServiceFactory.createFromCustomConfig(
        16000,
        BleAudioCodec.pcm16,
        'en',
        config,
        primarySocketFactory: (_, __, ___) => primary,
        secondaryServiceFactory: (_, __, ___, {String? source}) {
          secondaryFactoryCalls++;
          throw StateError('localOnly must not construct the Omi secondary service: $source');
        },
      );
      final receivedSegments = <TranscriptSegment>[];
      service.subscribe('local-only-factory-test', _RecordingListener(onSegments: receivedSegments.addAll));

      expect(service.socket, isA<LocalOnlyTranscriptionSocket>());
      expect(service.socket, isNot(isA<CompositeTranscriptionSocket>()));
      await service.start();
      primary.emitMessage(
        jsonEncode([
          {
            'id': 'factory-s1',
            'text': 'primary transcript remains visible',
            'speaker': 'SPEAKER_00',
            'is_user': false,
            'start': 0.0,
            'end': 1.0,
          },
        ]),
      );

      expect(primary.connectCalls, 1);
      expect(secondaryFactoryCalls, 0);
      expect(receivedSegments.single.text, 'primary transcript remains visible');
    });

    test('full and transcriptOnly retain the existing composite behavior', () {
      const fullConfig = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        privacyPolicy: SttPrivacyPolicy.full,
      );
      const transcriptOnlyConfig = CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        privacyPolicy: SttPrivacyPolicy.transcriptOnly,
      );

      final fullService = TranscriptSocketServiceFactory.createFromCustomConfig(
        16000,
        BleAudioCodec.pcm16,
        'en',
        fullConfig,
      );
      final transcriptOnlyService = TranscriptSocketServiceFactory.createFromCustomConfig(
        16000,
        BleAudioCodec.pcm16,
        'en',
        transcriptOnlyConfig,
      );

      expect(fullService.socket, isA<CompositeTranscriptionSocket>());
      expect((fullService.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isTrue);
      expect(transcriptOnlyService.socket, isA<CompositeTranscriptionSocket>());
      expect((transcriptOnlyService.socket as CompositeTranscriptionSocket).forwardRawAudioToSecondary, isFalse);
    });
  });

  test('localOnly blocks the separate Omi speech-profile socket path', () async {
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        url: 'wss://stt.example.test/live',
        privacyPolicy: SttPrivacyPolicy.localOnly,
      ),
    );

    final socket = SocketServicePool();
    final speechProfile = await socket.speechProfile(codec: BleAudioCodec.pcm16, sampleRate: 16000, language: 'en');

    expect(speechProfile, isNull);
  });

  test('malformed persisted Custom STT config fails privacy-closed', () async {
    await SharedPreferencesUtil().saveString('customSttConfig', '{not-json');

    final config = SharedPreferencesUtil().customSttConfig;

    expect(config.provider, SttProvider.omi);
    expect(config.privacyPolicy, SttPrivacyPolicy.localOnly);
    expect(config.forwardsRawAudioToOmi, isFalse);
  });

  test('semantically invalid persisted Custom STT config fails privacy-closed', () async {
    for (final rawConfig in ['{}', '{"provider":"bogus"}']) {
      await SharedPreferencesUtil().saveString('customSttConfig', rawConfig);

      final config = SharedPreferencesUtil().customSttConfig;

      expect(config.provider, SttProvider.omi);
      expect(config.privacyPolicy, SttPrivacyPolicy.localOnly);
      expect(config.forwardsRawAudioToOmi, isFalse);
    }
  });

  test('conversation pool drops a request whose policy is already stale', () async {
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.localOnly,
      ),
    );
    final pool = SocketServicePool();

    final socket = await pool.socket(
      codec: BleAudioCodec.pcm16,
      sampleRate: 16000,
      language: 'en',
      customSttConfig: const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.full,
      ),
    );

    expect(socket, isNull);
  });

  test('localOnly revalidation after waiting on the mutex prevents speech socket creation', () async {
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.full,
      ),
    );

    final mutex = Mutex();
    await mutex.acquire();
    var factoryCalls = 0;
    final pool = SocketServicePool(
      mutex: mutex,
      speechProfileFactory: (_, __, ___, {String? source}) {
        factoryCalls++;
        return TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', _FakeSocket());
      },
    );

    final pending = pool.speechProfile(codec: BleAudioCodec.pcm16, sampleRate: 16000, language: 'en');
    await Future<void>.delayed(Duration.zero);
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.localOnly,
      ),
    );
    mutex.release();

    expect(await pending, isNull);
    expect(factoryCalls, 0);
  });

  test('awaited speech-profile stop closes an active socket on localOnly transition', () async {
    final speechSocket = _FakeSocket();
    final pool = SocketServicePool(
      speechProfileFactory: (_, __, ___, {String? source}) {
        return TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', speechSocket);
      },
    );

    final created = await pool.speechProfile(codec: BleAudioCodec.pcm16, sampleRate: 16000, language: 'en');
    expect(created, isNotNull);
    expect(speechSocket.connectCalls, 1);

    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.localOnly,
      ),
    );
    await pool.stopSpeechProfile();

    expect(speechSocket.stopCalls, 1);
    expect(speechSocket.status, PureSocketStatus.disconnected);
  });

  test('speech-profile revalidates policy after stopping the previous socket', () async {
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(
        provider: SttProvider.customLive,
        privacyPolicy: SttPrivacyPolicy.full,
      ),
    );
    final speechSocket = _FakeSocket();
    var factoryCalls = 0;
    final pool = SocketServicePool(
      speechProfileFactory: (_, __, ___, {String? source}) {
        factoryCalls++;
        return TranscriptSegmentSocketService.withSocket(16000, BleAudioCodec.pcm16, 'en', speechSocket);
      },
    );

    expect(await pool.speechProfile(codec: BleAudioCodec.pcm16, sampleRate: 16000, language: 'en'), isNotNull);
    speechSocket.onStop = () => SharedPreferencesUtil().saveCustomSttConfig(
          const CustomSttConfig(
            provider: SttProvider.customLive,
            privacyPolicy: SttPrivacyPolicy.localOnly,
          ),
        );

    expect(await pool.speechProfile(codec: BleAudioCodec.pcm16, sampleRate: 16000, language: 'en'), isNull);
    expect(factoryCalls, 1);
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
  int connectCalls = 0;
  int disconnectCalls = 0;
  int stopCalls = 0;
  Future<void> Function()? onStop;

  @override
  PureSocketStatus get status => _status;

  @override
  Future<bool> connect() async {
    connectCalls++;
    _status = PureSocketStatus.connected;
    _listener?.onConnected();
    return true;
  }

  @override
  Future<void> disconnect() async {
    disconnectCalls++;
    _status = PureSocketStatus.disconnected;
  }

  @override
  Future<void> stop() async {
    stopCalls++;
    await disconnect();
    await onStop?.call();
  }

  @override
  void onClosed([int? closeCode]) => _listener?.onClosed(closeCode);

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

  void emitMessage(dynamic message) => _listener?.onMessage(message);
  void emitConnected() => _listener?.onConnected();
  void emitClosed([int? closeCode]) => _listener?.onClosed(closeCode);
  void emitError(Object err) => _listener?.onError(err, StackTrace.current);
}

class _RecordingPureSocketListener implements IPureSocketListener {
  int connectedCount = 0;
  final List<int?> closedCodes = [];
  final List<Object> errors = [];

  @override
  void onConnected() => connectedCount++;

  @override
  void onMessage(dynamic message) {}

  @override
  void onClosed([int? closeCode]) => closedCodes.add(closeCode);

  @override
  void onError(Object err, StackTrace trace) => errors.add(err);
}

class _RecordingListener implements ITransctiptSegmentSocketServiceListener {
  _RecordingListener({required this.onSegments});

  final void Function(List<TranscriptSegment> segments) onSegments;

  @override
  void onSegmentReceived(List<TranscriptSegment> segments) => onSegments(segments);

  @override
  void onMessageEventReceived(MessageEvent event) {}

  @override
  void onConnected() {}

  @override
  void onClosed([int? closeCode]) {}

  @override
  void onError(Object err) {}
}
