/// A first message sent while the chat history is still loading ("Reading your memories…") stays
/// on screen with its reply: the load used to replace the list when it landed, leaving only Omi's
/// greeting (IMG_1159).
library;

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';

ServerMessage _message(String id, String text, MessageSender sender, DateTime at) =>
    ServerMessage(id, at, text, sender, MessageType.text, null, false, [], [], []);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  List<String> lines(MessageProvider provider) =>
      provider.messages.map((m) => '${m.sender == MessageSender.human ? 'me' : 'omi'}: ${m.text}').toList();

  test('a message sent while the history loads stays, with its reply', () async {
    final history = Completer<List<ServerMessage>>();
    final reply = Completer<void>();
    final greeting =
        _message('g', 'Hey Ashwin!', MessageSender.ai, DateTime.now().subtract(const Duration(minutes: 1)));
    final provider = MessageProvider()
      ..historyLoaderOverride = (({String? appId, bool dropdownSelected = false}) => history.future)
      ..replyStreamOverride = (text, {appId, filesId, context}) async* {
        yield ServerMessageChunk('r', 'Hi! ', MessageChunkType.data);
        await reply.future;
        yield ServerMessageChunk('r', '', MessageChunkType.done,
            message: _message('r', 'Hi! How can I help?', MessageSender.ai, DateTime.now()));
      };

    final load = provider.refreshMessages();
    provider.addMessageLocally('hello');
    final send = provider.sendMessageStreamToServer('hello');
    await pumpEventQueue();

    history.complete([greeting]);
    await load;
    expect(lines(provider).take(2), ['omi: Hey Ashwin!', 'me: hello'], reason: 'the load keeps what was sent');

    reply.complete();
    await send;
    expect(lines(provider), ['omi: Hey Ashwin!', 'me: hello', 'omi: Hi! How can I help?'],
        reason: 'the finished reply lands in its own place, not over the message before it');
  });

  test('a load that already has the sent message does not show it twice', () async {
    final history = Completer<List<ServerMessage>>();
    final provider = MessageProvider()
      ..historyLoaderOverride = (({String? appId, bool dropdownSelected = false}) => history.future)
      ..replyStreamOverride = (text, {appId, filesId, context}) async* {
        yield ServerMessageChunk('r', 'Hi!', MessageChunkType.data);
      };

    final load = provider.refreshMessages();
    final sentAt = DateTime.now();
    provider.addMessageLocally('hello');
    await provider.sendMessageStreamToServer('hello');
    history.complete([_message('server-hello', 'hello', MessageSender.human, sentAt)]);
    await load;

    expect(provider.messages.where((m) => m.sender == MessageSender.human), hasLength(1));
    expect(provider.messages.last.text, 'Hi!');
  });
}
