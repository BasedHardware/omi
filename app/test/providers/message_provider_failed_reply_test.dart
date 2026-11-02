/// A failed chat reply shows a localized error with Try Again instead of the raw server text, and
/// Try Again resends the user's message (mobile UX contract, lane 3 #16).
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/providers/message_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a network failure marks the reply failed, hides the raw text and can be retried', () async {
    final sent = <String>[];
    var fail = true;
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        sent.add(text);
        if (fail) throw Exception('socket closed');
        yield ServerMessageChunk('reply-1', 'All good.', MessageChunkType.data);
      };

    provider.addMessageLocally('hello');
    await provider.sendMessageStreamToServer('hello');

    final failed = provider.messages.last;
    expect(failed.sender, MessageSender.ai);
    expect(provider.isReplyFailed(failed), isTrue);
    expect(provider.canRetryReply(failed), isTrue);
    expect(failed.text, isEmpty, reason: 'the raw English server message is no longer shown');
    expect(provider.sendingMessage, isFalse);

    fail = false;
    await provider.retryFailedReply(failed);

    expect(sent, ['hello', 'hello'], reason: 'Try Again resends the same user message');
    expect(provider.messages.where((m) => identical(m, failed)), isEmpty);
    expect(provider.messages.where((m) => m.sender == MessageSender.human), hasLength(1),
        reason: 'retrying does not duplicate the user bubble');
    final retried = provider.messages.last;
    expect(provider.isReplyFailed(retried), isFalse);
    expect(retried.text, 'All good.');
  });

  test('a server error chunk is treated as a failed reply, not shown verbatim', () async {
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('x', 'Internal Server Error: stack trace', MessageChunkType.error);
      };

    await provider.sendMessageStreamToServer('hi');

    final reply = provider.messages.last;
    expect(provider.isReplyFailed(reply), isTrue);
    expect(reply.text, isEmpty);
  });

  test('Try Again while chat is paused keeps the failed reply and releases the composer', () async {
    final sent = <String>[];
    var fail = true;
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        sent.add(text);
        if (fail) throw Exception('socket closed');
        yield ServerMessageChunk('reply-1', 'All good.', MessageChunkType.data);
      };
    provider.addMessageLocally('hello');
    await provider.sendMessageStreamToServer('hello');
    final failed = provider.messages.last;

    // The budget check pauses chat while the failed reply is still on screen.
    final resetAt = DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch ~/ 1000;
    provider
        .applyChatAtCap(ChatAtCap(title: 'Paused', body: 'Budget used', resetLine: 'Resets soon', resetAt: resetAt));
    // The chat page locks the composer before it calls retry.
    provider.setSendingMessage(true);
    await provider.retryFailedReply(failed);

    expect(sent, ['hello'], reason: 'nothing is sent while chat is paused');
    expect(provider.messages.last, same(failed), reason: 'the failed reply stays instead of vanishing');
    expect(provider.isReplyFailed(failed), isTrue);
    expect(provider.canRetryReply(failed), isTrue);
    expect(provider.sendingMessage, isFalse, reason: 'the composer is usable again once the pause ends');

    provider.applyChatAtCap(null);
    fail = false;
    provider.setSendingMessage(true);
    await provider.retryFailedReply(failed);

    expect(sent, ['hello', 'hello']);
    expect(provider.messages.last.text, 'All good.');
    expect(provider.sendingMessage, isFalse);
  });

  test('retry is a no-op for a reply that did not fail', () async {
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        yield ServerMessageChunk('x', 'fine', MessageChunkType.data);
      };
    await provider.sendMessageStreamToServer('hi');
    final reply = provider.messages.last;
    final count = provider.messages.length;

    await provider.retryFailedReply(reply);

    expect(provider.messages.length, count);
  });
}
