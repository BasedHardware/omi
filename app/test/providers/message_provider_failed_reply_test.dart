/// A failed chat reply shows a localized error with Try Again instead of the raw server text, and
/// Try Again resends the user's message (mobile UX contract, lane 3 #16).
library;

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

  test('a network failure marks the reply failed, hides the raw text and can be retried', () async {
    final sent = <String>[];
    var fail = true;
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context}) async* {
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
      ..replyStreamOverride = (text, {appId, filesId, context}) async* {
        yield ServerMessageChunk('x', 'Internal Server Error: stack trace', MessageChunkType.error);
      };

    await provider.sendMessageStreamToServer('hi');

    final reply = provider.messages.last;
    expect(provider.isReplyFailed(reply), isTrue);
    expect(reply.text, isEmpty);
  });

  test('retry is a no-op for a reply that did not fail', () async {
    final provider = MessageProvider()
      ..replyStreamOverride = (text, {appId, filesId, context}) async* {
        yield ServerMessageChunk('x', 'fine', MessageChunkType.data);
      };
    await provider.sendMessageStreamToServer('hi');
    final reply = provider.messages.last;
    final count = provider.messages.length;

    await provider.retryFailedReply(reply);

    expect(provider.messages.length, count);
  });
}
