import 'dart:async';

import 'package:async/async.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _RecordingAnalyticsAdapter implements AnalyticsAdapter {
  final List<(String, Map<String, Object>?)> events = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add((eventName, properties));

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}

class _FakeWebSocketSink implements WebSocketSink {
  final _done = Completer<void>();

  @override
  void add(Object? event) {}

  @override
  void addError(Object error, [StackTrace? stackTrace]) {}

  @override
  Future addStream(Stream stream) => Future.value();

  @override
  Future close([int? closeCode, String? closeReason]) => _done.future;

  @override
  Future get done => _done.future;
}

class _FakeWebSocketChannel implements WebSocketChannel {
  final StreamController<Object?> incoming = StreamController<Object?>.broadcast();
  final sent = <Object?>[];
  final _FakeWebSocketSink outgoing = _FakeWebSocketSink();

  @override
  Stream get stream => incoming.stream;

  @override
  WebSocketSink get sink => _RecordingSink(outgoing, sent);

  @override
  String? get protocol => null;

  @override
  int? get closeCode => null;

  @override
  String? get closeReason => null;

  @override
  Future<void> get ready => Future.value();

  @override
  // Unused by PhoneCallProvider; kept non-abstract for the interface only.
  StreamChannel<S> cast<S>() => throw UnimplementedError();

  @override
  StreamChannel<Object?> changeSink(StreamSink<Object?> Function(StreamSink<Object?>) change) =>
      throw UnimplementedError();

  @override
  StreamChannel<Object?> changeStream(Stream<Object?> Function(Stream<Object?>) change) => throw UnimplementedError();

  @override
  void pipe(StreamChannel<Object?> other) => throw UnimplementedError();

  @override
  StreamChannel<S> transform<S>(StreamChannelTransformer<S, Object?> transformer) => throw UnimplementedError();

  @override
  StreamChannel<Object?> transformSink(StreamSinkTransformer<Object?, Object?> transformer) =>
      throw UnimplementedError();

  @override
  StreamChannel<Object?> transformStream(StreamTransformer<Object?, Object?> transformer) => throw UnimplementedError();
}

class _RecordingSink implements WebSocketSink {
  _RecordingSink(this._inner, this.sent);

  final _FakeWebSocketSink _inner;
  final List<Object?> sent;

  @override
  void add(Object? event) {
    sent.add(event);
    _inner.add(event);
  }

  @override
  void addError(Object error, [StackTrace? stackTrace]) => _inner.addError(error, stackTrace);

  @override
  Future addStream(Stream stream) => _inner.addStream(stream);

  @override
  Future close([int? closeCode, String? closeReason]) => _inner.close(closeCode, closeReason);

  @override
  Future get done => _inner.done;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const eventChannelName = 'com.omi/phone_calls/events';
  const codec = StandardMethodCodec();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late _RecordingAnalyticsAdapter analytics;

  Future<void> emitEvent(Object? event) {
    return messenger.handlePlatformMessage(
      eventChannelName,
      codec.encodeSuccessEnvelope(event),
      (ByteData? data) {},
    );
  }

  setUp(() async {
    analytics = _RecordingAnalyticsAdapter();
    AnalyticsManager.resetForTesting();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    messenger.setMockMessageHandler(eventChannelName, (ByteData? message) async {
      return codec.encodeSuccessEnvelope(null);
    });
  });

  tearDown(() {
    messenger.setMockMessageHandler(eventChannelName, null);
    AnalyticsManager.resetForTesting();
    Env.clearApiBaseUrlOverrideForTesting();
    PhoneCallProvider.socketFactoryForTesting = null;
    PhoneCallProvider.headerBuilderForTesting = null;
  });

  test('WS connected with zero audio frames surfaces noAudio instead of silence', () async {
    final socket = _FakeWebSocketChannel();
    PhoneCallProvider.socketFactoryForTesting = (_, __) => socket;
    PhoneCallProvider.headerBuilderForTesting = (_) async => <String, String>{};

    final provider = PhoneCallProvider.forTesting();
    provider.debugSetCallIdForTesting('call-1');
    provider.noAudioStallTimeout = const Duration(milliseconds: 150);
    addTearDown(provider.dispose);

    await Future<void>.delayed(const Duration(milliseconds: 50));
    // Simulate the native layer reporting an active call.
    await emitEvent({'type': 'callStateChanged', 'state': 'active'});
    await Future<void>.delayed(const Duration(milliseconds: 100));
    socket.incoming.add('ping'); // server accepted the socket
    await Future<void>.delayed(const Duration(milliseconds: 100));

    expect(provider.transcriptionStatus, TranscriptionStatus.active);

    await Future<void>.delayed(const Duration(milliseconds: 300));

    expect(provider.transcriptionStatus, TranscriptionStatus.noAudio);
    expect(
      analytics.events.map((event) => event.$1),
      contains('Phone Call Transcript Session'),
    );
    final stall = analytics.events.firstWhere((event) => event.$1 == 'Phone Call Transcript Session');
    expect(stall.$2?['ws_accepted'], true);
    expect(stall.$2?['audio_frames_sent'], 0);
    expect(stall.$2?['reason'], 'no_audio_stall');
  });

  test('hangup with zero frames still reports the transcript session with zeros', () async {
    final socket = _FakeWebSocketChannel();
    PhoneCallProvider.socketFactoryForTesting = (_, __) => socket;
    PhoneCallProvider.headerBuilderForTesting = (_) async => <String, String>{};

    final provider = PhoneCallProvider.forTesting();
    provider.debugSetCallIdForTesting('call-1');
    provider.noAudioStallTimeout = const Duration(seconds: 60); // no stall in this scenario
    addTearDown(provider.dispose);

    await Future<void>.delayed(const Duration(milliseconds: 50));
    await emitEvent({'type': 'callStateChanged', 'state': 'active'});
    await Future<void>.delayed(const Duration(milliseconds: 100));
    socket.incoming.add('ping');
    await Future<void>.delayed(const Duration(milliseconds: 200));

    await emitEvent({'type': 'callStateChanged', 'state': 'ended'});
    await Future<void>.delayed(const Duration(milliseconds: 100));

    expect(
      analytics.events.map((event) => event.$1),
      contains('Phone Call Transcript Session'),
    );
    final session = analytics.events.firstWhere((event) => event.$1 == 'Phone Call Transcript Session');
    expect(session.$2?['audio_frames_sent'], 0);
    expect(session.$2?['audio_bytes_sent'], 0);
    expect(session.$2?['audio_channel_1_frames'], 0);
    expect(session.$2?['audio_channel_2_frames'], 0);
    expect(session.$2?['transcription_status_final'], 'active', reason: 'status at the moment of hangup');
  });
}
