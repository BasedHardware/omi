import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/gen/apps_wire.g.dart' as wire;
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';

ChatSessionSummary _session(String id) =>
    ChatSessionSummary(id: id, title: 'Thread $id', updatedAt: DateTime.utc(2026));

ServerMessage _message(String id, {MessageSender sender = MessageSender.human}) =>
    ServerMessage(id, DateTime.utc(2026), id, sender, MessageType.text, null, false, [], [], []);

class _FakeSessions extends ChatSessionsApi {
  @override
  Future<ApiResult<ChatSessionSummary>> create() async => ApiSuccess(_session('new'));

  @override
  Future<ApiResult<List<ServerMessage>>> messages(String id, {int offset = 0, int limit = 100}) async =>
      ApiSuccess([_message(id)]);

  @override
  Future<ApiResult<void>> delete(String id) async => const ApiSuccess<void>(null);

  @override
  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) async => const ApiSuccess('Title');
}

wire.GeneratedAppSearchResponse _appsPage(List<wire.GeneratedAppCatalogItem> apps, {bool hasNext = false}) {
  return wire.GeneratedAppSearchResponse(
    data: apps,
    filters: const wire.GeneratedAppSearchFilters(sort: 'popular'),
    pagination: wire.GeneratedAppPagination(
      count: apps.length,
      hasNext: hasNext,
      hasPrevious: false,
      limit: 100,
      offset: 0,
      total: apps.length,
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    Env.init(const _EnvFields());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a send supersedes a pending history load so a late read cannot clobber the turn', () async {
    final pending = Completer<List<ServerMessage>>();
    final provider = MessageProvider(sessionsApi: _FakeSessions());
    provider.legacyMessagesLoader = ({appId, dropdownSelected = false}) => pending.future;
    provider.replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
      yield ServerMessageChunk('reply', 'answer', MessageChunkType.data);
      yield ServerMessageChunk(
        'reply',
        '',
        MessageChunkType.done,
        message: _message('ai-1', sender: MessageSender.ai),
      );
    };
    addTearDown(provider.dispose);

    final refresh = provider.refreshMessages();
    await Future.microtask(() {});
    expect(provider.isLoadingMessages, isTrue);

    provider.addMessageLocally('question');
    await provider.sendMessageStreamToServer('question');
    expect(provider.isLoadingMessages, isFalse);

    pending.complete([_message('late-history')]);
    await refresh;

    expect(provider.messages.map((m) => m.id), containsAll(['ai-1']));
    expect(provider.messages.any((m) => m.text == 'question'), isTrue);
    expect(provider.messages.any((m) => m.id == 'late-history'), isFalse);
  });

  group('classified reply failures', () {
    for (final kind in [
      ChatStreamFailureClass.offline,
      ChatStreamFailureClass.server,
      ChatStreamFailureClass.timeout,
      ChatStreamFailureClass.notSignedIn,
      ChatStreamFailureClass.unknown,
    ]) {
      test('transport failure ${kind.name} marks the reply failed with its class', () async {
        final provider = MessageProvider(sessionsApi: _FakeSessions())
          ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
            throw ChatStreamException(kind);
          };
        addTearDown(provider.dispose);

        provider.addMessageLocally('question');
        await provider.sendMessageStreamToServer('question');

        final reply = provider.messages.last;
        expect(provider.isReplyFailed(reply), isTrue);
        expect(provider.replyFailure(reply), kind);
        expect(provider.canRetryReply(reply), isTrue);
        expect(provider.sendingMessage, isFalse);
        expect(provider.showTypingIndicator, isFalse);
      });
    }

    test('a timeout error frame marks the reply as a timeout', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          yield ServerMessageChunk('reply', 'The response took too long. Please try again.', MessageChunkType.error,
              errorCode: 'timeout');
        };
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      expect(provider.replyFailure(provider.messages.last), ChatStreamFailureClass.timeout);
    });

    for (final (code, kind) in [
      ('offline', ChatStreamFailureClass.offline),
      ('server_error', ChatStreamFailureClass.server),
      ('not_signed_in', ChatStreamFailureClass.notSignedIn),
      ('unlisted_code', ChatStreamFailureClass.server),
    ]) {
      test('typed error code $code maps to ${kind.name}', () async {
        final provider = MessageProvider(sessionsApi: _FakeSessions())
          ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
            yield ServerMessageChunk('reply', 'bounded message', MessageChunkType.error, errorCode: code);
          };
        addTearDown(provider.dispose);

        provider.addMessageLocally('question');
        await provider.sendMessageStreamToServer('question');

        expect(provider.replyFailure(provider.messages.last), kind);
      });
    }

    test('a stream error is terminal: a later fallback done cannot mark success', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          yield ServerMessageChunk(
              'reply', 'Unable to complete the response. Please try again.', MessageChunkType.error);
          yield ServerMessageChunk(
            'reply',
            '',
            MessageChunkType.done,
            message: _message('ai-done', sender: MessageSender.ai),
          );
        };
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      final reply = provider.messages.last;
      expect(provider.isReplyFailed(reply), isTrue);
      expect(provider.replyFailure(reply), ChatStreamFailureClass.server);
      expect(provider.messages.any((m) => m.id == 'ai-done'), isFalse);
    });

    test('an empty stream marks the reply as a server failure and releases the composer', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {};
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      final reply = provider.messages.last;
      expect(provider.isReplyFailed(reply), isTrue);
      expect(provider.replyFailure(reply), ChatStreamFailureClass.server);
      expect(provider.sendingMessage, isFalse);
    });

    test('quota keeps the localized reply instead of a failure marker', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          yield ServerMessageChunk(
            'reply',
            jsonEncode({'error': 'quota_exceeded'}),
            MessageChunkType.error,
          );
        };
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      final reply = provider.messages.last;
      expect(provider.isReplyFailed(reply), isFalse);
      expect(reply.text, isNotEmpty);
      expect(provider.isChatQuotaExceeded, isTrue);
    });

    test('a quota error code is honored even when the body is not parseable', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          yield ServerMessageChunk('reply', '{}', MessageChunkType.error, errorCode: 'quota_exceeded');
        };
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      final reply = provider.messages.last;
      expect(provider.isReplyFailed(reply), isFalse);
      expect(provider.isChatQuotaExceeded, isTrue);
    });

    test('a stream that delivers data but never sends done keeps the partial answer', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions())
        ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
          yield ServerMessageChunk('reply', 'partial answer', MessageChunkType.data);
        };
      addTearDown(provider.dispose);

      provider.addMessageLocally('question');
      await provider.sendMessageStreamToServer('question');

      final reply = provider.messages.last;
      expect(provider.isReplyFailed(reply), isFalse);
      expect(reply.text, 'partial answer');
      expect(provider.sendingMessage, isFalse);
    });

    for (final (body, name) in [
      (
        'error: {"error":"quota_exceeded","message":"quota_exceeded"}\n\n'
            'done: eyJpZCI6ICJhaS1jYW5uZWQiLCAiY3JlYXRlZF9hdCI6ICIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsICJzZW5kZXIiOiAiYWkiLCAidGV4dCI6ICJjYW5uZWQgcmVwbHkiLCAidHlwZSI6ICJ0ZXh0In0=\n\n',
        'quota_exceeded',
      ),
      (
        'error: {"error":"server_error","message":"quota_accounting_unavailable"}\n\n'
            'done: eyJpZCI6ICJhaS1jYW5uZWQiLCAiY3JlYXRlZF9hdCI6ICIyMDI2LTAxLTAxVDAwOjAwOjAwWiIsICJzZW5kZXIiOiAiYWkiLCAidGV4dCI6ICJjYW5uZWQgcmVwbHkiLCAidHlwZSI6ICJ0ZXh0In0=\n\n',
        'server_error',
      ),
    ]) {
      test('a negotiated wire $name frame drives the real stream client', () async {
        var protocol = '';
        final provider = MessageProvider(sessionsApi: _FakeSessions())
          ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
            final seams = ApiStreamingSeams(
              transport: (request) async {
                protocol = request.headers['X-Omi-Chat-Failure-Protocol'] ?? '';
                return http.StreamedResponse(Stream.value(utf8.encode(body)), 200);
              },
              headers: (request) async => <String, String>{'Authorization': 'Bearer token', ...request.headers},
            );
            yield* sendMessageStreamServer(text, seams: seams);
          };
        addTearDown(provider.dispose);

        provider.addMessageLocally('question');
        await provider.sendMessageStreamToServer('question');

        final reply = provider.messages.last;
        expect(protocol, '1');
        if (name == 'quota_exceeded') {
          expect(provider.isChatQuotaExceeded, isTrue);
          expect(provider.isReplyFailed(reply), isFalse);
          expect(reply.text, contains('monthly limit'));
        } else {
          expect(provider.isReplyFailed(reply), isTrue);
          expect(provider.replyFailure(reply), ChatStreamFailureClass.server);
          expect(provider.canRetryReply(reply), isTrue);
        }
        expect(provider.showTypingIndicator, isFalse);
        expect(provider.sendingMessage, isFalse);
      });
    }
  });

  test('retry resends the original text, context, and file ids', () async {
    final sends = <({String text, List<String>? filesId, ChatPageContext? context})>[];
    var attempts = 0;
    final provider = MessageProvider(sessionsApi: _FakeSessions())
      ..replyStreamOverride = (text, {appId, filesId, context, chatSessionId}) async* {
        attempts++;
        sends.add((text: text, filesId: filesId, context: context));
        if (attempts == 1) throw const ChatStreamException(ChatStreamFailureClass.offline);
        yield ServerMessageChunk(
          'reply',
          '',
          MessageChunkType.done,
          message: _message('ai-retry', sender: MessageSender.ai),
        );
      };
    provider.uploadedFiles
        .add(MessageFile('openai-id', null, 'doc.pdf', 'application/pdf', 'file-1', DateTime.utc(2026), null));
    addTearDown(provider.dispose);

    provider.addMessageLocally('question');
    await provider.sendMessageStreamToServer('question',
        context: const ChatPageContext(type: 'conversation', id: 'c1'));

    final failed = provider.messages.last;
    expect(provider.canRetryReply(failed), isTrue);
    await provider.retryFailedReply(failed);

    expect(sends, hasLength(2));
    expect(sends.first.text, sends.last.text);
    expect(sends.first.filesId, sends.last.filesId);
    expect(sends.last.filesId, ['file-1']);
    expect(sends.last.context?.type, 'conversation');
    expect(provider.messages.last.id, 'ai-retry');
    expect(provider.messages.where((m) => m.sender == MessageSender.human), hasLength(1));
  });

  test('worksWithChat accepts chat and persona apps', () {
    App build(Set<String> capabilities) => App(
          id: 'a',
          name: 'n',
          author: '',
          description: '',
          image: '',
          capabilities: capabilities,
          status: 'approved',
          category: 'other',
          approved: true,
          ratingCount: 0,
          enabled: true,
          deleted: false,
          isPaid: false,
          isUserPaid: false,
        );

    expect(build({'chat'}).worksWithChat(), isTrue);
    expect(build({'persona'}).worksWithChat(), isTrue);
    expect(build({'memories'}).worksWithChat(), isFalse);
  });

  group('fetchChatApps', () {
    test('a failed fetch retains the prior list and exposes the problem', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions());
      provider.chatAppsLoaderOverride = ({offset = 0, limit = 50}) async => ApiSuccess(
            _appsPage(const [
              wire.GeneratedAppCatalogItem(id: 'chat-app', capabilities: ['chat'], enabled: true)
            ]),
          );
      addTearDown(provider.dispose);
      await provider.fetchChatApps();
      expect(provider.chatApps, hasLength(1));
      expect(provider.chatAppsProblem, isNull);

      provider.chatAppsLoaderOverride =
          ({offset = 0, limit = 50}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport));
      await provider.fetchChatApps();

      expect(provider.chatApps, hasLength(1));
      expect(provider.chatAppsProblem?.kind, ApiProblemKind.transport);
    });

    test('pagination loads every installed page and filters to chat-capable apps', () async {
      final pages = <int>{0, 100};
      final provider = MessageProvider(sessionsApi: _FakeSessions());
      provider.chatAppsLoaderOverride = ({offset = 0, limit = 50}) async {
        pages.remove(offset);
        return offset == 0
            ? ApiSuccess(_appsPage(const [
                wire.GeneratedAppCatalogItem(id: 'chat-app', capabilities: ['chat'], enabled: true),
                wire.GeneratedAppCatalogItem(id: 'memories-app', capabilities: ['memories'], enabled: true),
              ], hasNext: true))
            : ApiSuccess(_appsPage(const [
                wire.GeneratedAppCatalogItem(id: 'persona-app', capabilities: ['persona'], enabled: true),
              ]));
      };
      addTearDown(provider.dispose);

      await provider.fetchChatApps();

      expect(pages, isEmpty);
      expect(provider.chatApps.map((a) => a.id), containsAll(['chat-app', 'persona-app']));
      expect(provider.chatApps.map((a) => a.id), isNot(contains('memories-app')));
      expect(provider.chatAppsProblem, isNull);
    });

    test('a failure on a later page retains the previously loaded list', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions());
      provider.chatAppsLoaderOverride = ({offset = 0, limit = 50}) async => ApiSuccess(
            _appsPage(const [
              wire.GeneratedAppCatalogItem(id: 'chat-app', capabilities: ['chat'], enabled: true)
            ]),
          );
      addTearDown(provider.dispose);
      await provider.fetchChatApps();
      expect(provider.chatApps, hasLength(1));

      provider.chatAppsLoaderOverride = ({offset = 0, limit = 50}) async => offset == 0
          ? ApiSuccess(_appsPage(const [
              wire.GeneratedAppCatalogItem(id: 'new-app', capabilities: ['chat'], enabled: true)
            ], hasNext: true))
          : const ApiFailure(ApiProblem(ApiProblemKind.server));
      await provider.fetchChatApps();

      expect(provider.chatApps.map((a) => a.id), ['chat-app']);
      expect(provider.chatAppsProblem?.kind, ApiProblemKind.server);
    });

    test('a genuine empty result clears a stale problem', () async {
      final provider = MessageProvider(sessionsApi: _FakeSessions());
      provider.chatAppsLoaderOverride =
          ({offset = 0, limit = 50}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport));
      addTearDown(provider.dispose);
      await provider.fetchChatApps();
      expect(provider.chatAppsProblem, isNotNull);

      provider.chatAppsLoaderOverride = ({offset = 0, limit = 50}) async => ApiSuccess(_appsPage(const []));
      await provider.fetchChatApps();

      expect(provider.chatApps, isEmpty);
      expect(provider.chatAppsProblem, isNull);
    });
  });

  group('retrieveInstalledChatApps', () {
    test('a malformed body is a decode failure, not an empty list', () async {
      final result = await retrieveInstalledChatApps(send: (_) async => http.Response('not json', 200));

      expect(result, isA<ApiFailure<wire.GeneratedAppSearchResponse>>());
      expect((result as ApiFailure<wire.GeneratedAppSearchResponse>).problem.kind, ApiProblemKind.decode);
    });

    test('a body missing required pagination fields is a decode failure', () async {
      final result = await retrieveInstalledChatApps(send: (_) async => http.Response('{"data": []}', 200));

      expect(result, isA<ApiFailure<wire.GeneratedAppSearchResponse>>());
      expect((result as ApiFailure<wire.GeneratedAppSearchResponse>).problem.kind, ApiProblemKind.decode);
    });

    test('a valid page decodes into the generated search response', () async {
      final result = await retrieveInstalledChatApps(
        send: (_) async => http.Response(
          jsonEncode({
            'data': [
              {
                'id': 'a1',
                'name': 'Notes',
                'capabilities': ['chat'],
                'enabled': true
              }
            ],
            'pagination': {'count': 1, 'hasNext': false, 'hasPrevious': false, 'limit': 100, 'offset': 0, 'total': 1},
            'filters': {'sort': 'popular'},
          }),
          200,
        ),
      );

      expect(result, isA<ApiSuccess<wire.GeneratedAppSearchResponse>>());
      expect((result as ApiSuccess<wire.GeneratedAppSearchResponse>).data.data?.single.id, 'a1');
    });
  });
}

final class _EnvFields implements EnvFields {
  const _EnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
