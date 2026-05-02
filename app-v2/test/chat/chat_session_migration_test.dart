import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:nooto_v2/chat/chat_message.dart';
import 'package:nooto_v2/chat/chat_provider.dart';
import 'package:nooto_v2/chat/chat_session.dart';
import 'package:nooto_v2/chat/chat_storage.dart';
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

/// Minimal stub — migration tests never trigger send/stream paths. If the
/// provider unexpectedly calls into the service, fail loudly instead of
/// silently returning empty data.
class _FakeChatService implements ChatService {
  @override
  Stream<ChatStreamEvent> streamChat(String message) {
    throw StateError(
      'streamChat must not be called during migration tests',
    );
  }

  @override
  noSuchMethod(Invocation invocation) {
    throw StateError(
      'Unexpected ChatService call: ${invocation.memberName}',
    );
  }
}

/// JSON shape that mirrors `ChatMessage.toJson()` but omits the `sessionId`
/// key — simulates pre-migration on-disk rows written before the field
/// existed.
Map<String, dynamic> _legacyMessageJson({
  required String id,
  required ChatRole role,
  required String text,
  required DateTime createdAt,
}) {
  return <String, dynamic>{
    'id': id,
    'role': role.name,
    'text': text,
    'createdAt': createdAt.toIso8601String(),
    // No sessionId — that's the whole point of "legacy".
  };
}

void main() {
  late Directory tempDir;

  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('chat_session_migration_test');
    PathProviderPlatform.instance = _FakePathProvider(tempDir.path);
    Hive.init(tempDir.path);
    await Hive.openBox<Map>(ChatBoxes.messages);
    await Hive.openBox<Map>(ChatBoxes.sessions);
  });

  tearDown(() async {
    await Hive.close();
    if (tempDir.existsSync()) {
      await tempDir.delete(recursive: true);
    }
  });

  group('ChatProvider migration from pre-sessions data', () {
    test(
      'REGRESSION — pre-migration messages get folded into a Welcome chat',
      () async {
        final msgBox = Hive.box<Map>(ChatBoxes.messages);

        // Five legacy messages, mixed roles, distinct timestamps. Insert in
        // non-chronological order to verify ascending sort on hydrate.
        final msgs = <Map<String, dynamic>>[
          _legacyMessageJson(
            id: 'm-3',
            role: ChatRole.assistant,
            text: 'Sure — what would you like to know?',
            createdAt: DateTime.parse('2026-04-30T10:00:30Z'),
          ),
          _legacyMessageJson(
            id: 'm-1',
            role: ChatRole.user,
            text: 'Hey, can you help me plan my week?',
            createdAt: DateTime.parse('2026-04-30T10:00:00Z'),
          ),
          _legacyMessageJson(
            id: 'm-5',
            role: ChatRole.assistant,
            text: 'Got it. I will draft a plan.',
            createdAt: DateTime.parse('2026-04-30T10:01:30Z'),
          ),
          _legacyMessageJson(
            id: 'm-2',
            role: ChatRole.assistant,
            text: 'Of course, happy to help!',
            createdAt: DateTime.parse('2026-04-30T10:00:15Z'),
          ),
          _legacyMessageJson(
            id: 'm-4',
            role: ChatRole.user,
            text: 'Focus on deep work blocks please.',
            createdAt: DateTime.parse('2026-04-30T10:01:00Z'),
          ),
        ];
        for (final m in msgs) {
          await msgBox.put(m['id'] as String, m);
        }

        final provider = ChatProvider(service: _FakeChatService());
        // Allow the constructor's _hydrate() microtask chain (notifyListeners,
        // any pending persistence) to settle.
        await Future<void>.delayed(Duration.zero);

        // Exactly one session, with the stable Welcome id.
        expect(provider.sessions, hasLength(1));
        expect(provider.sessions.single.id, 'welcome-chat');

        // messageCount reflects all 5 migrated rows.
        expect(provider.sessions.single.messageCount, 5);

        // Title derives from the first user message (earliest by createdAt).
        const firstUserText = 'Hey, can you help me plan my week?';
        expect(
          provider.sessions.single.title,
          deriveSessionTitle(firstUserText),
        );

        // Selecting Welcome surfaces all 5 messages, ordered ascending.
        provider.selectSession('welcome-chat');
        expect(provider.messages, hasLength(5));
        for (var i = 1; i < provider.messages.length; i++) {
          expect(
            provider.messages[i].createdAt.isAfter(
              provider.messages[i - 1].createdAt,
            ),
            isTrue,
            reason: 'messages should be sorted ascending by createdAt',
          );
        }

        // On disk: every message row now has sessionId == 'welcome-chat'.
        final persisted = msgBox.values.toList();
        expect(persisted, hasLength(5));
        for (final raw in persisted) {
          final json = Map<String, dynamic>.from(raw);
          expect(
            json['sessionId'],
            'welcome-chat',
            reason: 'migration must tag every legacy row on disk',
          );
        }

        provider.dispose();
      },
    );

    test(
      'REGRESSION — second hydrate is idempotent (no duplicate Welcome chats)',
      () async {
        final msgBox = Hive.box<Map>(ChatBoxes.messages);
        final sessionBox = Hive.box<Map>(ChatBoxes.sessions);

        // Three legacy messages, sessionId-less.
        await msgBox.put(
          'a-1',
          _legacyMessageJson(
            id: 'a-1',
            role: ChatRole.user,
            text: 'Question one',
            createdAt: DateTime.parse('2026-04-30T09:00:00Z'),
          ),
        );
        await msgBox.put(
          'a-2',
          _legacyMessageJson(
            id: 'a-2',
            role: ChatRole.assistant,
            text: 'Answer one',
            createdAt: DateTime.parse('2026-04-30T09:00:10Z'),
          ),
        );
        await msgBox.put(
          'a-3',
          _legacyMessageJson(
            id: 'a-3',
            role: ChatRole.user,
            text: 'Question two',
            createdAt: DateTime.parse('2026-04-30T09:00:20Z'),
          ),
        );

        // First hydrate: creates the Welcome chat.
        final p1 = ChatProvider(service: _FakeChatService());
        await Future<void>.delayed(Duration.zero);

        expect(p1.sessions, hasLength(1));
        expect(p1.sessions.single.id, 'welcome-chat');
        p1.dispose();

        // Second hydrate against the same boxes — must NOT create a duplicate.
        final p2 = ChatProvider(service: _FakeChatService());
        await Future<void>.delayed(Duration.zero);

        expect(p2.sessions, hasLength(1));
        expect(p2.sessions.single.id, 'welcome-chat');
        expect(p2.sessions.single.messageCount, 3);

        // No duplicate row on disk either.
        expect(sessionBox.length, 1);

        p2.dispose();
      },
    );

    test(
      'brand-new install with empty boxes does NOT create a Welcome chat',
      () async {
        // Both boxes are open and empty (setUp guarantees this).
        final provider = ChatProvider(service: _FakeChatService());
        await Future<void>.delayed(Duration.zero);

        expect(provider.sessions, isEmpty);
        expect(provider.currentSessionId, isNull);

        // And nothing should have been written to disk.
        expect(Hive.box<Map>(ChatBoxes.sessions).length, 0);
        expect(Hive.box<Map>(ChatBoxes.messages).length, 0);

        provider.dispose();
      },
    );
  });
}
