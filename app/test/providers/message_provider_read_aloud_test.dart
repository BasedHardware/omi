import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/voice_playback/chat_reply_read_aloud.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
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

class _FakeSessions extends ChatSessionsApi {
  @override
  Future<ApiResult<ChatSessionSummary>> create() async =>
      ApiSuccess(ChatSessionSummary(id: 's1', title: 'Chat', updatedAt: DateTime.utc(2026)));

  @override
  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) async => const ApiSuccess('Title');
}

class _FakeSpeaker implements ChatReplySpeaker {
  final List<String> calls = [];
  final List<String> interrupts = [];

  @override
  Future<void> beginResponse({required String messageId, bool Function()? canBegin}) async =>
      calls.add('begin:$messageId');

  @override
  void updateStreamingResponse({required String messageId, required String fullText, required bool isFinal}) =>
      calls.add('update:$messageId:$isFinal:$fullText');

  @override
  Future<void> interruptResponse({
    required String messageId,
    required VoiceReplyPlaybackInterruptSource source,
  }) async =>
      interrupts.add(messageId);
}

ServerMessage _ai(String id, String text) =>
    ServerMessage(id, DateTime.utc(2026), text, MessageSender.ai, MessageType.text, null, false, [], [], []);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/package_info'),
      (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'},
    );
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'test-device-hash', 'uid': 'uid-a'});
    await SharedPreferencesUtil.init();
    await PlatformManager.initializeServices();
  });

  MessageProvider buildProvider(
    _FakeSpeaker speaker,
    Stream<ServerMessageChunk> Function() stream, {
    bool enabled = true,
  }) {
    var playbackSerial = 0;
    return MessageProvider(
      sessionsApi: _FakeSessions(),
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      readAloud: ChatReplyReadAloud(
        speaker: speaker,
        isEnabled: () => enabled,
        playbackId: () => 'chat:test-${playbackSerial++}',
      )..active = true,
    )..replyStreamOverride = (_, {appId, filesId, context, chatSessionId}) => stream();
  }

  test('typed reply: only the final done chunk is voiced, once', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', 'Partial ', MessageChunkType.data);
      yield ServerMessageChunk('r1', 'text.', MessageChunkType.data);
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'Partial text.'));
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);

    expect(speaker.calls, ['begin:chat:test-0', 'update:chat:test-0:true:Partial text.']);
  });

  test('error and quota chunks never voice anything', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', 'boom', MessageChunkType.error);
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls, isEmpty);
  });

  test('a quota_exceeded error body stays silent', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', '{"error":"quota_exceeded"}', MessageChunkType.error);
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls, isEmpty);
    expect(provider.isChatQuotaExceeded, isTrue);
  });

  test('duplicate done chunks voice exactly once', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'Answer.'));
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'Answer.'));
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls.where((c) => c.startsWith('begin:')), hasLength(1));
    expect(speaker.calls.where((c) => c.startsWith('update:')), hasLength(1));
  });

  test('an incomplete stream without done stays silent', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', 'Trailing partial', MessageChunkType.data);
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls, isEmpty);
  });

  test('a new typed query revokes the previous owned playback', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'First answer.'));
    });
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('First?');
    await Future<void>.delayed(Duration.zero);
    await provider.sendMessageStreamToServer('Second?');
    await Future<void>.delayed(Duration.zero);

    expect(speaker.interrupts, ['chat:test-0']);
    expect(speaker.calls.where((c) => c.startsWith('update:')), [
      'update:chat:test-0:true:First answer.',
      'update:chat:test-1:true:First answer.',
    ]);
  });

  test('disabled preference stays silent even on a completed reply', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'Answer.'));
    }, enabled: false);
    addTearDown(provider.dispose);

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls, isEmpty);
  });

  test('dispose revokes owned playback', () async {
    final speaker = _FakeSpeaker();
    final provider = buildProvider(speaker, () async* {
      yield ServerMessageChunk('r1', '', MessageChunkType.done, message: _ai('r1', 'Answer.'));
    });

    await provider.sendMessageStreamToServer('Hello?');
    await Future<void>.delayed(Duration.zero);
    expect(speaker.calls, isNotEmpty);
    provider.dispose();
    await Future<void>.delayed(Duration.zero);
    expect(speaker.interrupts, ['chat:test-0']);
  });
}
