import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/sync_provider.dart';

ServerConversation _conversation({
  required DateTime createdAt,
  DateTime? startedAt,
  required String id,
}) {
  return ServerConversation(
    id: id,
    createdAt: createdAt,
    startedAt: startedAt,
    structured: Structured('Title', 'Overview'),
  );
}

SyncedConversationPointer _pointer(ServerConversation conversation, int index) {
  return SyncedConversationPointer(
    type: SyncedConversationType.newConversation,
    index: index,
    key: conversation.startedAt ?? conversation.createdAt,
    conversation: conversation,
  );
}

void main() {
  test(
    'offline sync results sort by recording time instead of upload time',
    () {
      final olderRecordingUploadedToday = _conversation(
        id: 'day-1',
        startedAt: DateTime.utc(2026, 3, 1, 20),
        createdAt: DateTime.utc(2026, 3, 2, 9),
      );
      final currentRecording = _conversation(
        id: 'day-2',
        startedAt: DateTime.utc(2026, 3, 2, 8),
        createdAt: DateTime.utc(2026, 3, 2, 8, 5),
      );

      final sorted = sortSyncedConversationPointers([
        _pointer(olderRecordingUploadedToday, 0),
        _pointer(currentRecording, 1),
      ]);

      expect(sorted.map((pointer) => pointer.conversation.id), [
        'day-2',
        'day-1',
      ]);
    },
  );

  test('falls back to creation time when recording time is unavailable', () {
    final older = _conversation(
      id: 'older',
      createdAt: DateTime.utc(2026, 3, 1),
    );
    final newer = _conversation(
      id: 'newer',
      createdAt: DateTime.utc(2026, 3, 2),
    );

    final sorted = sortSyncedConversationPointers([
      _pointer(older, 0),
      _pointer(newer, 1),
    ]);

    expect(sorted.map((pointer) => pointer.conversation.id), [
      'newer',
      'older',
    ]);
  });
}
