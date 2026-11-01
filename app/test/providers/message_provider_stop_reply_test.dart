/// Stop ends the reply in progress, and a new message replaces a reply that is still
/// running, so a typo can be corrected without waiting for the wrong answer.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('Stop while the reply is still thinking ends the turn and removes the empty bubble', () async {
    final never = Completer<void>();
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r', 'Searching files', MessageChunkType.think);
        await never.future; // the server is still working
      };

    provider.addMessageLocally('Do you see this is one steel frame?');
    final turn = provider.sendMessageStreamToServer('Do you see this is one steel frame?');
    await pumpEventQueue();
    expect(provider.canStopReply, isTrue);
    expect(provider.messages.last.sender, MessageSender.ai);

    await provider.stopReply();
    await turn;

    expect(provider.canStopReply, isFalse);
    expect(provider.showTypingIndicator, isFalse);
    expect(provider.sendingMessage, isFalse);
    expect(provider.messages, hasLength(1), reason: 'the empty AI placeholder is removed');
    expect(provider.messages.single.sender, MessageSender.human);
  });

  test('Stop after text started keeps what was shown and is not a failure', () async {
    final never = Completer<void>();
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r', 'I see one continuous shot', MessageChunkType.data);
        await never.future;
      };

    final turn = provider.sendMessageStreamToServer('describe it');
    await Future<void>.delayed(const Duration(milliseconds: 150)); // let the text flush
    await provider.stopReply();
    await turn;

    final reply = provider.messages.last;
    expect(reply.sender, MessageSender.ai);
    expect(reply.text, 'I see one continuous shot');
    expect(provider.isReplyFailed(reply), isFalse);
  });

  test('a stopped reply that errors while unwinding is still a stop, not a failure', () async {
    final aborted = Completer<void>();
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r', 'Partial', MessageChunkType.data);
        await aborted.future;
        throw const SocketException('aborted');
      };

    final turn = provider.sendMessageStreamToServer('hi');
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final stopped = provider.stopReply();
    aborted.complete();
    await stopped;
    await turn;

    expect(provider.isReplyFailed(provider.messages.last), isFalse);
  });

  test('a new message stops the running reply and is answered next', () async {
    final sent = <String>[];
    final never = Completer<void>();
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        sent.add(text);
        if (text.contains('steel')) {
          yield ServerMessageChunk('r1', 'thinking', MessageChunkType.think);
          await never.future;
        }
        yield ServerMessageChunk('r2', 'Here is the progression.', MessageChunkType.data);
        yield ServerMessageChunk('r2', '', MessageChunkType.done,
            message: ServerMessage('r2', DateTime.utc(2026), 'Here is the progression.', MessageSender.ai,
                MessageType.text, null, false, [], [], []));
      };

    provider.addMessageLocally('one steel frame?');
    final first = provider.sendMessageStreamToServer('one steel frame?');
    await pumpEventQueue();

    await provider.stopReply(superseded: true);
    await first;
    expect(provider.chatMutationInProgress, isFalse, reason: 'the composer is free for the correction');

    provider.addMessageLocally('Sorry, I meant still frame');
    await provider.sendMessageStreamToServer('Sorry, I meant still frame');

    expect(sent, ['one steel frame?', 'Sorry, I meant still frame']);
    expect(
        provider.messages.map((m) => m.sender).toList(), [MessageSender.human, MessageSender.human, MessageSender.ai],
        reason: 'both questions stay in the thread; only the replacement is answered');
    expect(provider.messages.last.text, 'Here is the progression.');
  });

  test('an error chunk that arrives with Stop does not mark the reply failed', () async {
    final release = Completer<void>();
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('r', 'Partial', MessageChunkType.data);
        await release.future;
        yield ServerMessageChunk('r', 'Internal error', MessageChunkType.error);
      };

    final turn = provider.sendMessageStreamToServer('hi');
    await Future<void>.delayed(const Duration(milliseconds: 150));
    release.complete(); // the error chunk is already on its way
    await provider.stopReply();
    await turn;

    expect(provider.isReplyFailed(provider.messages.last), isFalse);
    expect(provider.messages.last.text, 'Partial');
  });

  test('stopReply with nothing running is a no-op', () async {
    final provider = MessageProvider();
    expect(provider.canStopReply, isFalse);
    await provider.stopReply();
    expect(provider.messages, isEmpty);
  });
}
