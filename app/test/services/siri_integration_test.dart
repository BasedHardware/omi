import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/services/siri_integration.dart';

class RecordingSiriHost extends SiriIndexApi {
  String? owner;
  List<SiriConversation> conversations = [];
  List<SiriMemory> memories = [];
  List<SiriTask> tasks = [];
  String? deletedType;
  List<String> deletedIds = [];

  @override
  Future<void> upsertConversations(String uid, List<SiriConversation> rows) async {
    owner = uid;
    conversations = rows;
  }

  @override
  Future<void> upsertMemories(String uid, List<SiriMemory> rows) async {
    owner = uid;
    memories = rows;
  }

  @override
  Future<void> upsertTasks(String uid, List<SiriTask> rows) async {
    owner = uid;
    tasks = rows;
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    owner = uid;
    deletedType = type;
    deletedIds = ids;
  }
}

class _RaceToken implements IdTokenResult {
  @override
  String? get token => 'fake-token';
  @override
  DateTime? get expirationTime => DateTime.now().add(const Duration(minutes: 5));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RaceUser implements User {
  @override
  String get uid => 'owner-race';
  @override
  Future<IdTokenResult> getIdTokenResult([bool forceRefresh = false]) async => _RaceToken();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RaceHost extends SiriIndexApi {
  final publishStarted = Completer<void>();
  final releasePublish = Completer<void>();
  String? owner;
  int generation = 0;

  @override
  Future<void> publishSessionConfig(SiriSessionConfig config) async {
    publishStarted.complete();
    await releasePublish.future;
    owner = config.uid;
  }

  @override
  Future<int> wipe() async {
    owner = null;
    return ++generation;
  }

  @override
  Future<List<SiriTelemetryRecord>> takeTelemetry() async => [];
}

void main() {
  final now = DateTime.now();

  test('sign-out ordered after an in-flight native session publication', () async {
    final host = _RaceHost();
    final siri = SiriIntegration.forTest(host, 'owner-race',
        sessionConfig: (user, token, generation) => SiriSessionConfig(
              uid: user.uid,
              generation: generation,
              baseUrl: 'http://127.0.0.1:8977',
              profile: 'local_dev',
              appVersion: 'test',
              appBuild: '0',
              deviceIdHash: 'test',
              token: token.token,
              tokenExpiresAtMs: token.expirationTime?.millisecondsSinceEpoch,
            ));
    final signingIn = siri.accountChanged(_RaceUser());
    await host.publishStarted.future.timeout(const Duration(seconds: 5));
    final signingOut = siri.accountChanged(null);
    host.releasePublish.complete();
    await Future.wait([signingIn, signingOut]);
    expect(host.owner, isNull);
  });

  test('conversation projection sorts newest and excludes old or unfinished rows', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-a');
    ServerConversation conversation(String id, int ageDays,
            {ConversationStatus status = ConversationStatus.completed}) =>
        ServerConversation(
          id: id,
          createdAt: now.subtract(Duration(days: ageDays)),
          structured: Structured('Title $id', 'Summary $id'),
          status: status,
        );

    await siri.upsertConversations([
      conversation('older', 10),
      conversation('unfinished', 1, status: ConversationStatus.processing),
      conversation('too-old', 181),
      conversation('newest', 1),
    ]);

    expect(host.owner, 'owner-a');
    expect(host.conversations.map((row) => row.id), ['newest', 'older']);
    expect(host.conversations.first.title, 'Title newest');
  });

  test('memory projection sorts newest and drops expired or deleted rows', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-b');
    Memory memory(String id, int ageDays, {bool deleted = false, DateTime? invalidAt}) => Memory(
          id: id,
          uid: 'owner-b',
          content: 'Content $id',
          category: MemoryCategory.manual,
          createdAt: now.subtract(Duration(days: ageDays)),
          updatedAt: now,
          visibility: MemoryVisibility.private,
          deleted: deleted,
          invalidAt: invalidAt,
        );

    await siri.upsertMemories([
      memory('older', 10),
      memory('expired', 2, invalidAt: now.subtract(const Duration(days: 1))),
      memory('deleted', 1, deleted: true),
      memory('newest', 0),
    ]);

    expect(host.owner, 'owner-b');
    expect(host.memories.map((row) => row.id), ['newest', 'older']);
    expect(host.memories.first.content, 'Content newest');
  });

  test('task projection keeps active tasks and recent completions with owner UID', () async {
    final host = RecordingSiriHost();
    final siri = SiriIntegration.forTest(host, 'owner-c');
    ActionItemWithMetadata task(String id, bool completed, DateTime? completedAt) => ActionItemWithMetadata(
          id: id,
          description: 'Task $id',
          completed: completed,
          createdAt: now.subtract(const Duration(days: 45)),
          completedAt: completedAt,
        );

    await siri.upsertTasks([
      task('active', false, null),
      task('recent', true, now.subtract(const Duration(days: 1))),
      task('expired', true, now.subtract(const Duration(days: 31))),
    ]);
    expect(host.owner, 'owner-c');
    expect(host.tasks.map((row) => row.id), ['active', 'recent']);
    expect(host.tasks.last.completed, isTrue);

    await siri.delete('task', 'active');
    expect(host.owner, 'owner-c');
    expect(host.deletedType, 'task');
    expect(host.deletedIds, ['active']);
  });
}
