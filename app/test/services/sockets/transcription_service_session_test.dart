import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({'uid': 'user-a'});
    await SharedPreferencesUtil.init();
    Env.init(_TestEnvFields());
  });

  test('reconnect URL reclaims the existing conversation id', () {
    final service = TranscriptSocketServiceFactory.createDefault(
      16000,
      BleAudioCodec.opus,
      'en',
      clientConversationId: '8fd118f7-9f5c-4d55-9caf-678ad6d3acb7',
    );

    final url = (service.socket as PureSocket).url;
    final uri = Uri.parse(url);
    expect(
      uri.queryParameters['client_conversation_id'],
      '8fd118f7-9f5c-4d55-9caf-678ad6d3acb7',
    );
  });

  test('replays the initial conversation session to a late subscriber', () {
    final socket = _FakePureSocket();
    final service = TranscriptSegmentSocketService.withSocket(
      16000,
      BleAudioCodec.opus,
      'en',
      socket,
    );

    service.onMessage(
      '''
      {
        "type": "conversation_session",
        "conversation_id": "conversation-a",
        "status": "in_progress",
        "recording_session_id": "recording-a",
        "lifecycle_version": 1,
        "lifecycle_phase": "in_progress",
        "lifecycle_sequence": 2
      }
      ''',
    );

    final listener = _RecordingListener();
    service.subscribe(listener, listener);

    expect(listener.events, hasLength(1));
    final event = listener.events.single as ConversationSessionEvent;
    expect(event.conversationId, 'conversation-a');
    expect(event.recordingSessionId, 'recording-a');
    expect(event.lifecycleVersion, 1);
    expect(event.lifecyclePhase, 'in_progress');
    expect(event.lifecycleSequence, 2);
    expect(event.isInProgress, isTrue);
  });

  test('does not replay a stopped socket session into a later capture', () async {
    final socket = _FakePureSocket();
    final service = TranscriptSegmentSocketService.withSocket(
      16000,
      BleAudioCodec.opus,
      'en',
      socket,
    );
    service.onMessage(
      '{"type":"conversation_session","conversation_id":"old","status":"in_progress"}',
    );

    await service.stop();
    final listener = _RecordingListener();
    service.subscribe(listener, listener);

    expect(listener.events, isEmpty);
  });

  test('does not report server ready from the transport connection alone', () async {
    final socket = _FakePureSocket();
    final service = TranscriptSegmentSocketService.withSocket(
      16000,
      BleAudioCodec.opus,
      'en',
      socket,
    );

    expect(service.serverReady, isFalse);
    expect(
      await service.waitUntilServerReady(timeout: const Duration(milliseconds: 1)),
      isFalse,
    );
  });

  test('waits for and replays the server ready status', () async {
    final socket = _FakePureSocket();
    final service = TranscriptSegmentSocketService.withSocket(
      16000,
      BleAudioCodec.opus,
      'en',
      socket,
    );

    final ready = service.waitUntilServerReady();
    service.onMessage('{"type":"service_status","status":"ready"}');

    expect(await ready, isTrue);
    expect(service.serverReady, isTrue);

    final listener = _RecordingListener();
    service.subscribe(listener, listener);
    expect(listener.events, hasLength(1));
    expect((listener.events.single as MessageServiceStatusEvent).status, 'ready');
  });

  test('STT failure rejects readiness and is replayed to a late subscriber', () async {
    final socket = _FakePureSocket();
    final service = TranscriptSegmentSocketService.withSocket(
      16000,
      BleAudioCodec.opus,
      'en',
      socket,
    );

    final ready = service.waitUntilServerReady();
    service.onMessage(
      '{"type":"service_status","status":"stt_failed","retryable":true}',
    );

    expect(await ready, isFalse);
    expect(service.serverReady, isFalse);

    final listener = _RecordingListener();
    service.subscribe(listener, listener);
    expect(listener.events, hasLength(1));
    final failure = listener.events.single as MessageServiceStatusEvent;
    expect(failure.status, 'stt_failed');
    expect(failure.retryable, isTrue);
  });
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  String? get googleMapsApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get openAIAPIKey => null;
  @override
  String? get posthogApiKey => null;
  @override
  bool? get useAuthCustomToken => false;
  @override
  bool? get useWebAuth => false;
}

class _RecordingListener implements ITransctiptSegmentSocketServiceListener {
  final List<MessageEvent> events = [];

  @override
  void onMessageEventReceived(MessageEvent event) => events.add(event);

  @override
  void onClosed([int? closeCode]) {}

  @override
  void onConnected() {}

  @override
  void onError(Object err) {}

  @override
  void onSegmentReceived(List<TranscriptSegment> segments) {}
}

class _FakePureSocket implements IPureSocket {
  IPureSocketListener? listener;

  @override
  PureSocketStatus get status => PureSocketStatus.connected;

  @override
  Future<bool> connect() async => true;

  @override
  Future<void> disconnect() async {}

  @override
  void onClosed() => listener?.onClosed();

  @override
  void onConnected() => listener?.onConnected();

  @override
  void onError(Object err, StackTrace trace) => listener?.onError(err, trace);

  @override
  void onMessage(message) => listener?.onMessage(message);

  @override
  void send(message) {}

  @override
  void setListener(IPureSocketListener listener) {
    this.listener = listener;
  }

  @override
  Future<void> stop() async {}
}
