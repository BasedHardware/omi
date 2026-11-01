import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/voice_playback/chat_reply_read_aloud.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

class _FakeSpeaker implements ChatReplySpeaker {
  final List<String> calls = [];
  final List<String> interrupts = [];
  Completer<void>? beginGate;
  Object? beginError;
  bool Function()? lastCanBegin;

  @override
  Future<void> beginResponse({required String messageId, bool Function()? canBegin}) async {
    lastCanBegin = canBegin;
    await beginGate?.future;
    if (canBegin != null && !canBegin()) {
      calls.add('begin-stale:$messageId');
      return;
    }
    calls.add('begin:$messageId');
    if (beginError != null) throw beginError!;
  }

  @override
  void updateStreamingResponse({required String messageId, required String fullText, required bool isFinal}) {
    calls.add('update:$messageId:$isFinal:${fullText.length}');
  }

  @override
  Future<void> interruptResponse({required String messageId, required VoiceReplyPlaybackInterruptSource source}) async {
    interrupts.add(messageId);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'uid-a'});
    await SharedPreferencesUtil.init();
  });

  test('default off: enabled getter is false until the owner opts in', () {
    expect(SharedPreferencesUtil().readChatRepliesAloud, isFalse);
    SharedPreferencesUtil().readChatRepliesAloud = true;
    expect(SharedPreferencesUtil().readChatRepliesAloud, isTrue);
  });

  test('read-aloud preference does not leak across account owners', () async {
    SharedPreferencesUtil().readChatRepliesAloud = true;
    SharedPreferences.setMockInitialValues({'uid': 'uid-b'});
    await SharedPreferencesUtil.init();
    expect(SharedPreferencesUtil().readChatRepliesAloud, isFalse);
  });

  test('toggle off is silent — nothing reaches the speaker', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => false, playbackId: () => 'chat:test');
    coordinator.active = true;
    await coordinator.readFinalReply('A complete reply.', generation: coordinator.generation);
    expect(speaker.calls, isEmpty);
  });

  test('enabled + active speaks the final reply exactly once', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:test');
    coordinator.active = true;
    await coordinator.readFinalReply('A complete reply.', generation: coordinator.generation);
    await coordinator.readFinalReply('A complete reply.', generation: coordinator.generation);
    expect(speaker.calls, ['begin:chat:test', 'update:chat:test:true:17']);
  });

  test('inactive screen never speaks', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true);
    await coordinator.readFinalReply('Reply.', generation: coordinator.generation);
    expect(speaker.calls, isEmpty);
  });

  test('a stale generation loses: newQuery invalidates a reply mid-begin', () async {
    final speaker = _FakeSpeaker()..beginGate = Completer<void>();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:stale');
    coordinator.active = true;
    final gen = coordinator.generation;
    final pending = coordinator.readFinalReply('Late reply.', generation: gen);
    coordinator.newQuery();
    speaker.beginGate!.complete();
    await pending;
    expect(speaker.calls, ['begin-stale:chat:stale']);
    expect(speaker.interrupts, ['chat:stale']);
  });

  test('deactivating mid-begin stops owned playback before update', () async {
    final speaker = _FakeSpeaker()..beginGate = Completer<void>();
    final coordinator = ChatReplyReadAloud(
      speaker: speaker,
      isEnabled: () => true,
      playbackId: () => 'chat:deactivate',
    );
    coordinator.active = true;
    final gen = coordinator.generation;
    final pending = coordinator.readFinalReply('Reply.', generation: gen);
    coordinator.active = false;
    speaker.beginGate!.complete();
    await pending;
    expect(speaker.calls, ['begin-stale:chat:deactivate']);
    expect(speaker.interrupts, ['chat:deactivate']);
  });

  test('revoke (sign-out / reset) invalidates pending and in-flight playback', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:revoke');
    coordinator.active = true;
    await coordinator.readFinalReply('Reply.', generation: coordinator.generation);
    coordinator.revoke();
    await Future<void>.delayed(Duration.zero);
    expect(speaker.interrupts, ['chat:revoke']);
    await coordinator.readFinalReply('Old reply.', generation: coordinator.generation - 1);
    expect(speaker.calls, hasLength(2));
  });

  test('owned cancel leaves other lifecycles alone', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:owned');
    coordinator.active = true;
    await coordinator.readFinalReply('Reply.', generation: coordinator.generation);
    await coordinator.cancel();
    expect(speaker.interrupts, ['chat:owned']);
  });

  test('empty replies never speak', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true);
    coordinator.active = true;
    await coordinator.readFinalReply('   ', generation: coordinator.generation);
    expect(speaker.calls, isEmpty);
  });

  test('concurrent finals for one generation begin exactly once', () async {
    final speaker = _FakeSpeaker();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:once');
    coordinator.active = true;
    final gen = coordinator.generation;
    await Future.wait([
      coordinator.readFinalReply('Reply.', generation: gen),
      coordinator.readFinalReply('Reply.', generation: gen),
      coordinator.readFinalReply('Reply.', generation: gen),
    ]);
    expect(speaker.calls, ['begin:chat:once', 'update:chat:once:true:6']);
  });

  test('a begin failure is best-effort — no throw, no update, id released', () async {
    final speaker = _FakeSpeaker()..beginError = StateError('tts down');
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:fail');
    coordinator.active = true;
    await coordinator.readFinalReply('Reply.', generation: coordinator.generation);
    expect(speaker.calls, ['begin:chat:fail']);
    expect(speaker.interrupts, isEmpty);
  });

  test('cancel revokes pending work and generation, not just the owned id', () async {
    final speaker = _FakeSpeaker()..beginGate = Completer<void>();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => true, playbackId: () => 'chat:cancel');
    coordinator.active = true;
    final gen = coordinator.generation;
    final pending = coordinator.readFinalReply('Reply.', generation: gen);
    await coordinator.cancel();
    speaker.beginGate!.complete();
    await pending;
    expect(speaker.calls, ['begin-stale:chat:cancel']);
    expect(speaker.calls.where((c) => c.startsWith('update:')), isEmpty);
    expect(coordinator.generation, greaterThan(gen));
  });

  test('toggling preference off mid-begin prevents the update', () async {
    var enabled = true;
    final speaker = _FakeSpeaker()..beginGate = Completer<void>();
    final coordinator = ChatReplyReadAloud(speaker: speaker, isEnabled: () => enabled, playbackId: () => 'chat:toggle');
    coordinator.active = true;
    final gen = coordinator.generation;
    final pending = coordinator.readFinalReply('Reply.', generation: gen);
    enabled = false;
    speaker.beginGate!.complete();
    await pending;
    expect(speaker.calls, ['begin-stale:chat:toggle']);
    expect(speaker.calls.where((c) => c.startsWith('update:')), isEmpty);
  });
}
