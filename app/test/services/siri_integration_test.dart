import 'package:flutter_test/flutter_test.dart';
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

void main() {
  final now = DateTime.now();

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
