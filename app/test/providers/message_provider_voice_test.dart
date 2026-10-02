import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
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

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/package_info'),
      (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'},
    );
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env is a late final singleton and may already be initialized in this isolate.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'test-device-hash'});
    await SharedPreferencesUtil.init();
    await PlatformManager.initializeServices();
  });

  test('typed no-speech reply becomes visible and invokes the failure-haptic callback', () async {
    var failureHaptics = 0;
    final provider = MessageProvider(
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) async* {
        yield ServerMessageChunk(
          'voice-message-id',
          'No speech was detected.',
          MessageChunkType.error,
          errorCode: 'no_speech',
        );
      },
    );

    await provider.sendVoiceMessageStreamToServer(
      [
        <int>[1, 2, 3]
      ],
      codec: BleAudioCodec.opus,
      onNoSpeech: () async => failureHaptics++,
    );

    expect(provider.messages, hasLength(1));
    expect(provider.messages.single.text, "Didn't catch that — try again");
    expect(provider.showTypingIndicator, isFalse);
    expect(failureHaptics, 1);
    provider.dispose();
  });

  test('pendant reply cannot append to an explicitly selected past thread', () async {
    final provider = MessageProvider(
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) async* {
        yield ServerMessageChunk('voice', 'Pendant answer', MessageChunkType.data);
      },
    );
    final prior = ServerMessage.empty()..text = 'Past thread';
    provider.chatSessionId = 'past';
    provider.messages = [prior];
    await provider.sendVoiceMessageStreamToServer([
      <int>[1]
    ], codec: BleAudioCodec.opus);
    expect(provider.messages, [prior]);
    expect(provider.messages.single.text, 'Past thread');
    expect(provider.canSwitchChat, isTrue);
    provider.dispose();
  });

  test('voice reply timeout clears the re-entry guard for the next question', () async {
    var streamCalls = 0;
    final stalled = StreamController<ServerMessageChunk>();
    final provider = MessageProvider(
      voiceReplyTimeout: const Duration(milliseconds: 10),
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) {
        streamCalls++;
        if (streamCalls == 1) return stalled.stream;
        return Stream.value(ServerMessageChunk('reply', 'Done.', MessageChunkType.data));
      },
    );

    await provider.sendVoiceMessageStreamToServer([
      <int>[1]
    ], codec: BleAudioCodec.opus);
    await provider.sendVoiceMessageStreamToServer([
      <int>[2]
    ], codec: BleAudioCodec.opus);

    expect(streamCalls, 2);
    expect(provider.showTypingIndicator, isFalse);
    await stalled.close();
    provider.dispose();
  });
}
