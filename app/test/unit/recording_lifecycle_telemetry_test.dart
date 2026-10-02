import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'https://api.example.test/';
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env is process-global and may already be initialized by another test.
    }
  });

  test('started and completed events share the recording UUID and measured duration', () {
    final events = <({String name, Map<String, dynamic> properties})>[];
    var now = DateTime.utc(2026, 8, 13, 12);
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-1',
      clock: () => now,
    );

    expect(telemetry.prepare(source: 'phone_mic_live'), 'recording-1');
    telemetry.markStarted();
    now = now.add(const Duration(milliseconds: 2750));
    telemetry.complete();

    expect(events.map((event) => event.name), [
      RecordingLifecycleTelemetry.startedEvent,
      RecordingLifecycleTelemetry.completedEvent,
    ]);
    expect(events.first.properties, {'recording_id': 'recording-1', 'recording_source': 'phone_mic_live'});
    expect(events.last.properties, {
      ...events.first.properties,
      'duration_seconds': 2.75,
      'reason': 'user_stopped',
      'audio_observed': false,
      'audio_observation_coverage': 'dart_ingress',
      'transcript_observed': false,
      'audio_bytes_observed': 0,
      'socket_bytes_submitted': 0,
      'socket_error_count': 0,
      'socket_connection_count': 0,
    });
    expect(telemetry.recordingId, isNull);
  });

  test('observations aggregate once and fence a recording across accounts', () {
    var epoch = 1;
    final events = <Map<String, dynamic>>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (_, properties) => events.add(properties),
      identityEpoch: () => epoch,
    );
    telemetry.prepare(source: 'phone_mic_live');
    telemetry.markStarted();
    telemetry.observeAudio(120);
    telemetry.observeAudio(240);
    telemetry.observeSent(100);
    telemetry.observeTranscript();
    telemetry.observeTranscript();
    telemetry.observeSocketError();
    telemetry.complete();
    expect(events.where((e) => e['stage'] == 'audio'), hasLength(1));
    expect(events.where((e) => e['stage'] == 'transcript'), hasLength(1));
    expect(events.last['audio_bytes_observed'], 360);
    expect(events.last['socket_bytes_submitted'], 100);
    expect(events.last['socket_error_count'], 1);
    telemetry.prepare(source: 'phone_mic_live');
    telemetry.markStarted();
    final before = events.length;
    epoch++;
    telemetry.observeAudio(10);
    telemetry.complete();
    expect(events.length, before);
  });

  test('native batch coverage explicitly distinguishes unobserved audio from empty capture', () {
    for (final source in ['phone_mic_batch', 'phone_mic_batch_auto']) {
      final events = <Map<String, dynamic>>[];
      final telemetry = RecordingLifecycleTelemetry(emitter: (_, properties) => events.add(properties));
      telemetry.prepare(source: source);
      telemetry.markStarted();
      telemetry.complete();
      expect(events.last['audio_observed'], false);
      expect(events.last['audio_observation_coverage'], 'native_batch_unavailable');
      expect(events.last, isNot(contains('outcome')));
      expect(events.last, isNot(contains('audio_lost')));
    }
  });

  test('zero and negative byte callbacks do not manufacture ingress evidence', () {
    final events = <Map<String, dynamic>>[];
    final telemetry = RecordingLifecycleTelemetry(emitter: (_, properties) => events.add(properties));
    telemetry.prepare(source: 'phone_mic_live');
    telemetry.markStarted();
    telemetry.observeAudio(0);
    telemetry.observeAudio(-1);
    telemetry.observeSent(-1);
    telemetry.complete();
    expect(events.last['audio_bytes_observed'], 0);
    expect(events.last['socket_bytes_submitted'], 0);
    expect(events.where((event) => event['stage'] == 'audio'), isEmpty);
  });

  test('failStart without a prepared session emits nothing', () {
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-unprepared',
    );

    telemetry.failStart(failureClass: 'capture_unavailable');

    expect(events, isEmpty);
    expect(telemetry.recordingId, isNull);
  });

  test('a denied capture emits a bounded start failure and no started event', () {
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-denied',
    );

    telemetry.prepare(source: 'phone_mic_batch');
    telemetry.failStart(failureClass: 'permission_denied');

    expect(events.single.name, RecordingLifecycleTelemetry.startFailedEvent);
    expect(events.single.properties, {
      'recording_id': 'recording-denied',
      'recording_source': 'phone_mic_batch',
      'failure_class': 'permission_denied',
    });
  });

  test('a prepared device start that never reaches capture emits capture_unavailable', () {
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-unavailable',
    );

    telemetry.prepare(source: 'pendant_live');
    telemetry.failStart(failureClass: 'capture_unavailable');

    expect(events.single.name, RecordingLifecycleTelemetry.startFailedEvent);
    expect(events.single.properties, {
      'recording_id': 'recording-unavailable',
      'recording_source': 'pendant_live',
      'failure_class': 'capture_unavailable',
    });
  });

  test('closing a prepared capture emits a bounded start failure', () {
    final events = <({String name, Map<String, dynamic> properties})>[];
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (name, properties) => events.add((name: name, properties: properties)),
      idFactory: () => 'recording-closed-before-start',
    );

    telemetry.prepare(source: 'pendant_live');
    telemetry.complete();

    expect(events.single.name, RecordingLifecycleTelemetry.startFailedEvent);
    expect(events.single.properties['failure_class'], 'pipeline_closed');
  });

  test('the recording UUID is attached to the authoritative listen request', () {
    final service = TranscriptSegmentSocketService.create(
      16000,
      BleAudioCodec.pcm16,
      'en',
      source: 'phone',
      clientConversationId: 'recording/with spaces',
    );

    final uri = Uri.parse((service.socket as PureSocket).url);
    expect(uri.path, '/v4/listen');
    expect(uri.queryParameters['client_conversation_id'], 'recording/with spaces');
  });

  test('telemetry failures never escape into capture behavior', () {
    final telemetry = RecordingLifecycleTelemetry(
      emitter: (_, __) => throw StateError('analytics unavailable'),
      idFactory: () => 'recording-safe',
    );

    expect(() {
      telemetry.prepare(source: 'pendant_live');
      telemetry.markStarted();
      telemetry.complete();
    }, returnsNormally);
  });
}
