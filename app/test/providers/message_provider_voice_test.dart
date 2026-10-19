import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

ServerMessage _voiceRow(String id, MessageSender sender, String text) =>
    ServerMessage(id, DateTime.now(), text, sender, MessageType.text, null, false, [], [], []);

/// What `/v2/voice-messages` streams for an answered pendant question: the transcribed
/// question, the answer text, then the saved answer.
Stream<ServerMessageChunk> _answeredVoiceQuestion() async* {
  yield ServerMessageChunk('question', '', MessageChunkType.message,
      message: _voiceRow('question', MessageSender.human, 'What did I promise Sam?'));
  yield ServerMessageChunk('answer', 'Call him on Friday.', MessageChunkType.data);
  yield ServerMessageChunk('answer', '', MessageChunkType.done,
      message: _voiceRow('answer', MessageSender.ai, 'Call him on Friday.'));
}

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

  test('pendant voice turn stays out of an open app thread such as Mentor', () async {
    // A Mentor notification opens chat on app 'mentor'. The voice endpoint has no app field, so
    // the backend saves the pendant question and its answer to the main Omi chat instead.
    final appProvider = AppProvider();
    addTearDown(appProvider.dispose);
    appProvider.setSelectedChatAppId('mentor');
    final provider = MessageProvider(
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) => _answeredVoiceQuestion(),
    );
    addTearDown(provider.dispose);
    provider.updateAppProvider(appProvider);
    final mentorTip = ServerMessage.empty(appId: 'mentor')..text = 'Mentor tip';
    provider.messages = [mentorTip];

    await provider.sendVoiceMessageStreamToServer([
      <int>[1]
    ], codec: BleAudioCodec.opus);

    expect(provider.messages, [mentorTip]);
    expect(provider.showTypingIndicator, isFalse);
    expect(provider.canSwitchChat, isTrue);
  });

  test('pendant voice turn still lands in the main chat after Omi is picked in the drawer', () async {
    final appProvider = AppProvider();
    addTearDown(appProvider.dispose);
    // The chat drawer's Omi row selects 'no_selected', which is the main chat.
    appProvider.setSelectedChatAppId('no_selected');
    final provider = MessageProvider(
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) => _answeredVoiceQuestion(),
    );
    addTearDown(provider.dispose);
    provider.updateAppProvider(appProvider);
    final earlier = ServerMessage.empty()..text = 'Earlier answer';
    provider.messages = [earlier];

    await provider.sendVoiceMessageStreamToServer([
      <int>[1]
    ], codec: BleAudioCodec.opus);

    expect(
      provider.messages.map((m) => m.text).toList(),
      ['Earlier answer', 'What did I promise Sam?', 'Call him on Friday.'],
    );
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
