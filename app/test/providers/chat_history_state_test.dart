import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';

ChatSessionSummary session(String id) => ChatSessionSummary(id: id, title: 'Thread $id', updatedAt: DateTime.utc(2026));
ServerMessage message(String id) =>
    ServerMessage(id, DateTime.utc(2026), id, MessageSender.human, MessageType.text, null, false, [], [], []);

class FakeSessions extends ChatSessionsApi {
  int creates = 0;
  int deletes = 0;
  final offsets = <int>[];
  Future<ApiResult<ChatSessionSummary>> Function()? createResult;
  Future<ApiResult<List<ServerMessage>>> Function(String, int)? readResult;
  ApiResult<void> deleteResult = const ApiSuccess<void>(null);
  @override
  Future<ApiResult<ChatSessionSummary>> create() async {
    creates++;
    return await createResult?.call() ?? ApiSuccess(session('new'));
  }

  @override
  Future<ApiResult<List<ServerMessage>>> messages(String id, {int offset = 0, int limit = 100}) async {
    offsets.add(offset);
    return await readResult?.call(id, offset) ?? ApiSuccess([message(id)]);
  }

  @override
  Future<ApiResult<void>> delete(String id) async {
    deletes++;
    return deleteResult;
  }

  @override
  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) async => const ApiSuccess('Title');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('opening history failure keeps the previous target and transcript', () async {
    final api = FakeSessions();
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    expect(await provider.openChatSession(session('first')), isTrue);
    api.readResult = (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.transport));
    expect(await provider.openChatSession(session('second')), isFalse);
    expect(provider.chatSessionId, 'first');
    expect(provider.messages.single.id, 'first');
    expect(provider.isLoadingMessages, isFalse);
    expect(provider.historyProblem, isNotNull);
  });

  test('a late history read cannot replace a newer selected thread', () async {
    final slow = Completer<ApiResult<List<ServerMessage>>>();
    final api = FakeSessions()
      ..readResult = (id, _) => id == 'slow' ? slow.future : Future.value(ApiSuccess([message(id)]));
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    final old = provider.openChatSession(session('slow'));
    expect(await provider.openChatSession(session('newest')), isTrue);
    slow.complete(ApiSuccess([message('stale')]));
    expect(await old, isFalse);
    expect(provider.chatSessionId, 'newest');
    expect(provider.messages.single.id, 'newest');
  });

  test('fresh chat invalidates pending reads and never revives the unscoped cache', () async {
    SharedPreferencesUtil().cachedMessages = [message('cached')];
    final slow = Completer<ApiResult<List<ServerMessage>>>();
    final api = FakeSessions()..readResult = (_, __) => slow.future;
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    final old = provider.openChatSession(session('old'));
    expect(provider.startFreshChat(), isTrue);
    provider.setMessagesFromCache();
    await provider.refreshMessages();
    slow.complete(ApiSuccess([message('late')]));
    expect(await old, isFalse);
    expect(provider.messages, isEmpty);
    expect(provider.chatSessionId, isNull);
    expect(provider.isFreshChat, isTrue);
  });

  test('failed session creation never sends into the server current session; retry creates first', () async {
    final api = FakeSessions()..createResult = () async => const ApiFailure(ApiProblem(ApiProblemKind.server));
    final sentTo = <String?>[];
    final provider = MessageProvider(sessionsApi: api)
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        sentTo.add(chatSessionId);
        yield ServerMessageChunk('reply', 'answer', MessageChunkType.data);
      };
    addTearDown(provider.dispose);
    provider.startFreshChat();
    provider.addMessageLocally('question');
    await provider.sendMessageStreamToServer('question');
    expect(sentTo, isEmpty);
    expect(provider.isFreshChat, isTrue);
    final failed = provider.messages.last;
    expect(provider.canRetryReply(failed), isTrue);
    api.createResult = () async => ApiSuccess(session('created'));
    await provider.retryFailedReply(failed);
    expect(sentTo, ['created']);
    expect(api.creates, 2);
    expect(provider.messages.where((m) => m.sender == MessageSender.human), hasLength(1));
  });

  test('session creation is single flight and thread switching is blocked during a stream', () async {
    final created = Completer<ApiResult<ChatSessionSummary>>();
    final api = FakeSessions()..createResult = () => created.future;
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    provider.startFreshChat();
    final first = provider.prepareChatSession();
    final duplicate = provider.prepareChatSession();
    expect(api.creates, 1);
    expect(provider.startFreshChat(), isFalse);
    created.complete(ApiSuccess(session('new')));
    await Future.wait([first, duplicate]);
    provider.setSendingMessage(true);
    expect(provider.startFreshChat(), isFalse);
    expect(await provider.openChatSession(session('other')), isFalse);
    expect(await provider.deleteChatSession('new'), isFalse);
    expect(api.deletes, 0);
  });

  test('reopened session sends and retry remain explicitly targeted without another create', () async {
    final api = FakeSessions();
    final ids = <String?>[];
    final provider = MessageProvider(sessionsApi: api)
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        ids.add(chatSessionId);
        yield ServerMessageChunk('reply', 'failure', MessageChunkType.error);
      };
    addTearDown(provider.dispose);
    await provider.openChatSession(session('past'));
    await provider.sendMessageStreamToServer('follow up');
    await provider.retryFailedReply(provider.messages.last);
    expect(ids, ['past', 'past']);
    expect(api.creates, 0);
  });

  test('older-message pagination deduplicates rows and exposes a retryable failure', () async {
    final api = FakeSessions()
      ..readResult = (_, offset) async =>
          ApiSuccess(offset == 0 ? List.generate(100, (i) => message('$i')) : [message('0'), message('older')]);
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await provider.openChatSession(session('past'));
    await provider.loadOlderMessages();
    expect(api.offsets, [0, 100]);
    expect(provider.messages, hasLength(101));
    expect(provider.hasOlderMessages, isFalse);
    provider.hasOlderMessages = true;
    api.readResult = (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.server));
    await provider.loadOlderMessages();
    expect(provider.messages, hasLength(101));
    expect(provider.historyProblem, isNotNull);
    expect(provider.loadingOlderMessages, isFalse);
    expect(provider.hasOlderMessages, isTrue);
  });

  test('switching while an older page is pending releases the new thread pagination', () async {
    final older = Completer<ApiResult<List<ServerMessage>>>();
    final api = FakeSessions()
      ..readResult = (id, offset) async {
        if (id == 'first' && offset > 0) return older.future;
        return ApiSuccess(List.generate(100, (i) => message('$id-$i')));
      };
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await provider.openChatSession(session('first'));
    final oldRead = provider.loadOlderMessages();
    expect(provider.loadingOlderMessages, isTrue);
    await provider.openChatSession(session('second'));
    expect(provider.loadingOlderMessages, isFalse);
    older.complete(ApiSuccess([message('stale')]));
    await oldRead;
    expect(provider.messages.any((m) => m.id == 'stale'), isFalse);
    await provider.loadOlderMessages();
    expect(api.offsets, [0, 100, 0, 100]);
  });

  test('pagination advances by server rows including rejected and duplicate rows', () async {
    final api = FakeSessions()
      ..readResult = (_, offset) async => ApiSuccess(List.generate(99, (i) => message('$i')), rejectedRows: 1);
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await provider.openChatSession(session('past'));
    expect(provider.historyProblem, isNotNull);
    await provider.loadOlderMessages();
    await provider.loadOlderMessages();
    expect(api.offsets, [0, 100, 200]);
    expect(provider.messages, hasLength(99));
  });

  test('deleting active thread starts fresh only after success', () async {
    final api = FakeSessions();
    final provider = MessageProvider(sessionsApi: api);
    addTearDown(provider.dispose);
    await provider.openChatSession(session('past'));
    api.deleteResult = const ApiFailure(ApiProblem(ApiProblemKind.server));
    expect(await provider.deleteChatSession('past'), isFalse);
    expect(provider.chatSessionId, 'past');
    api.deleteResult = const ApiSuccess<void>(null);
    expect(await provider.deleteChatSession('past'), isTrue);
    expect(provider.chatSessionId, isNull);
    expect(provider.messages, isEmpty);
    expect(provider.isFreshChat, isTrue);
  });

  test('disposing while a history read is pending suppresses notification and replacement', () async {
    final slow = Completer<ApiResult<List<ServerMessage>>>();
    final api = FakeSessions()..readResult = (_, __) => slow.future;
    final provider = MessageProvider(sessionsApi: api);
    final read = provider.openChatSession(session('past'));
    provider.dispose();
    slow.complete(ApiSuccess([message('late')]));
    expect(await read, isFalse);
  });
}
