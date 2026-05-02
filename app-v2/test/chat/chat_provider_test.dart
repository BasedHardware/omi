import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/chat_service.dart';

class _FakePathProvider extends PathProviderPlatform {
  _FakePathProvider(this.tempDir);
  final String tempDir;
  @override
  Future<String?> getApplicationDocumentsPath() async => tempDir;
  @override
  Future<String?> getApplicationSupportPath() async => tempDir;
  @override
  Future<String?> getTemporaryPath() async => tempDir;
}

/// Test fake for [ChatService] that emits a caller-supplied stream of events.
///
/// Two construction shapes:
///   * [_FakeChatService.fromEvents] — emit a finite list of events then close.
///   * [_FakeChatService.controlled]  — driven by a [StreamController] the test
///     can manually emit on / close (used for stream-cancellation tests).
class _FakeChatService extends ChatService {
  _FakeChatService._(this._streamFactory)
      : super(
          client: ApiClient(
            httpClient: MockClient((_) async => http.Response('', 200)),
            getIdToken: ({bool forceRefresh = false}) async => 'tok',
            signOut: () async {},
            baseUrl: 'https://example.test/',
          ),
        );

  factory _FakeChatService.fromEvents(List<ChatStreamEvent> events) {
    return _FakeChatService._(() => Stream<ChatStreamEvent>.fromIterable(events));
  }

  factory _FakeChatService.controlled(StreamController<ChatStreamEvent> controller) {
    return _FakeChatService._(() => controller.stream);
  }

  final Stream<ChatStreamEvent> Function() _streamFactory;
  int callCount = 0;

  @override
  Stream<ChatStreamEvent> streamChat(String prompt) {
    callCount += 1;
    return _streamFactory();
  }
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('chat_provider_test');
    PathProviderPlatform.instance = _FakePathProvider(tempDir.path);
    Hive.init(tempDir.path);
  });

  setUp(() async {
    if (!Hive.isBoxOpen(ChatBoxes.messages)) {
      await Hive.openBox<Map>(ChatBoxes.messages);
    }
    if (!Hive.isBoxOpen(ChatBoxes.sessions)) {
      await Hive.openBox<Map>(ChatBoxes.sessions);
    }
    await Hive.box<Map>(ChatBoxes.messages).clear();
    await Hive.box<Map>(ChatBoxes.sessions).clear();
  });

  tearDownAll(() async {
    await Hive.deleteFromDisk();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  group('ChatProvider session lifecycle', () {
    test('newSession() creates a session with currentSessionId set and messages empty',
        () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const []),
      );

      final id = provider.newSession();

      expect(provider.sessions, hasLength(1));
      expect(provider.currentSessionId, id);
      expect(provider.currentSessionId, provider.sessions.first.id);
      expect(provider.messages, isEmpty);
    });

    test('selectSession(valid_id) swaps the visible thread', () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const [ChatStreamText('hi back')]),
      );

      final aId = provider.newSession();
      // Send a message in A so it has visible content.
      await provider.send('hello A');
      expect(provider.messages, isNotEmpty);

      final bId = provider.newSession();
      expect(provider.currentSessionId, bId);
      expect(provider.messages, isEmpty);

      // Switch back to A — its messages should reappear.
      provider.selectSession(aId);
      expect(provider.currentSessionId, aId);
      expect(provider.messages, isNotEmpty);
      expect(provider.messages.first.text, 'hello A');
    });

    test('selectSession(invalid_id) is a no-op', () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const []),
      );

      final id = provider.newSession();
      provider.selectSession('does-not-exist');

      expect(provider.currentSessionId, id);
    });

    test('renameSession persists new title', () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const []),
      );

      final id = provider.newSession();
      final ok = await provider.renameSession(id, 'My new name');

      expect(ok, isTrue);
      final session = provider.sessions.firstWhere((s) => s.id == id);
      expect(session.title, 'My new name');
    });

    test('renameSession rejects empty title', () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const []),
      );

      final id = provider.newSession();
      final originalTitle = provider.sessions.firstWhere((s) => s.id == id).title;

      final ok = await provider.renameSession(id, '   ');

      expect(ok, isFalse);
      final session = provider.sessions.firstWhere((s) => s.id == id);
      expect(session.title, originalTitle);
    });

    test(
        'deleteSession removes session and its messages; clears active if it was the active one',
        () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const [ChatStreamText('reply')]),
      );

      final id = provider.newSession();
      await provider.send('hello');
      expect(provider.messages, isNotEmpty);

      await provider.deleteSession(id);

      expect(provider.sessions, isEmpty);
      expect(provider.currentSessionId, isNull);
      expect(provider.messages, isEmpty);
    });

    test('togglePin flips the pinned flag idempotently', () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const []),
      );

      final id = provider.newSession();
      expect(provider.sessions.firstWhere((s) => s.id == id).pinned, isFalse);

      await provider.togglePin(id);
      expect(provider.sessions.firstWhere((s) => s.id == id).pinned, isTrue);

      await provider.togglePin(id);
      expect(provider.sessions.firstWhere((s) => s.id == id).pinned, isFalse);
    });

    test('send() auto-titles the session from the first user message (one-shot)',
        () async {
      final provider = ChatProvider(
        service: _FakeChatService.fromEvents(const [ChatStreamText('Paris.')]),
      );

      final id = provider.newSession();
      await provider.send('What is the capital of France?');

      // Title was auto-derived from the first user message.
      var session = provider.sessions.firstWhere((s) => s.id == id);
      expect(session.title, 'What is the capital of France?');

      // User renames the session manually.
      final ok = await provider.renameSession(id, 'Travel planning');
      expect(ok, isTrue);

      // Subsequent send should NOT clobber the user-chosen title — the
      // auto-title gate is one-shot (only fires for the first user message).
      await provider.send('And of Spain?');

      session = provider.sessions.firstWhere((s) => s.id == id);
      expect(session.title, 'Travel planning');
    });
  });

  group('ChatProvider stream cancellation', () {
    test(
        'selectSession during a stream cancels the prior stream and finalizes the assistant message',
        () async {
      final controller = StreamController<ChatStreamEvent>();
      final provider = ChatProvider(
        service: _FakeChatService.controlled(controller),
      );

      final aId = provider.newSession();

      // Start sending in A but don't await — stream is open and waiting.
      final sendFuture = provider.send('hi');

      // Let the user message + initial assistant placeholder land.
      await Future<void>.delayed(Duration.zero);

      // Emit one chunk so the assistant message has some text.
      controller.add(const ChatStreamText('partial'));
      await Future<void>.delayed(Duration.zero);

      // Snapshot A's assistant text mid-stream for the no-growth assertion.
      final aMessagesBefore = provider.messages;
      final assistantBefore = aMessagesBefore.last;
      final textAtSwitch = assistantBefore.text;
      expect(assistantBefore.text, 'partial');

      // Switch to B mid-stream — provider should cancel the active stream
      // and finalize the assistant message in A.
      final bId = provider.newSession();
      provider.selectSession(bId);

      // Emit another chunk after the switch — A must NOT receive it.
      controller.add(const ChatStreamText(' AFTER_SWITCH'));
      await Future<void>.delayed(Duration.zero);

      // Switch back to A and inspect the finalized assistant message.
      provider.selectSession(aId);
      final aMessagesAfter = provider.messages;
      final finalizedAssistant = aMessagesAfter.last;

      expect(finalizedAssistant.streaming, isFalse);
      expect(finalizedAssistant.text, textAtSwitch,
          reason: 'cancelled stream must not write more chunks to A');

      // Clean up: close controller and let the original send promise settle.
      await controller.close();
      try {
        await sendFuture;
      } catch (_) {
        // Cancelled subscription may surface as a completed-with-cancellation
        // path; either resolution is fine.
      }
    });

    test('stopActiveStream marks the assistant message as stopped', () async {
      final controller = StreamController<ChatStreamEvent>();
      final provider = ChatProvider(
        service: _FakeChatService.controlled(controller),
      );

      provider.newSession();

      // Start streaming but don't await — the controller stays open.
      final sendFuture = provider.send('hi');

      // Let the user + assistant placeholder land.
      await Future<void>.delayed(Duration.zero);

      // Emit a couple of chunks so there's partial text to mark stopped.
      controller.add(const ChatStreamText('Hello'));
      controller.add(const ChatStreamText(' there'));
      await Future<void>.delayed(Duration.zero);

      // User taps "Stop generating".
      provider.stopActiveStream();

      // Let the awaiting send() future unblock and run its finally cleanup.
      await Future<void>.delayed(Duration.zero);

      // The assistant message should be finalized and marked stopped.
      final assistant = provider.messages.last;
      expect(assistant.streaming, isFalse);
      expect(assistant.stopped, isTrue);
      expect(provider.sending, isFalse);

      // Drain the original send promise cleanly.
      await controller.close();
      try {
        await sendFuture;
      } catch (_) {
        // Controlled stream cancellation is acceptable.
      }
    });
  });
}
