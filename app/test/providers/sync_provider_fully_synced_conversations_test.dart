import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/conversation_sync_utils.dart';

ServerConversation _convo(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 7, 18, 12, 0),
      structured: Structured('Title', 'Overview'),
      status: ConversationStatus.completed,
    );

Wal _wal({
  required String conversationId,
  required WalStatus status,
  required int timerStart,
}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.pcm16,
    seconds: 60,
    status: status,
    device: 'phone',
    conversationId: conversationId,
  );
}

void main() {
  test('filters out synced conversations that still have uploaded/pending WALs', () {
    final c1 = _convo('c1');
    final c2 = _convo('c2');

    final p1 = ConversationSyncUtils.createPointer(c1, SyncedConversationType.newConversation);
    final p2 = ConversationSyncUtils.createPointer(c2, SyncedConversationType.newConversation);

    final wals = [
      _wal(conversationId: c1.id, status: WalStatus.uploaded, timerStart: 1000),
      _wal(conversationId: c2.id, status: WalStatus.synced, timerStart: 2000),
    ];

    final filtered = SyncProvider.filterFullySyncedConversations(
      conversations: [p1, p2],
      wals: wals,
    );

    expect(filtered.map((p) => p.conversation.id), ['c2']);
  });

  test('keeps a synced conversation if there are no local WALs yet', () {
    final c1 = _convo('c1');
    final p1 = ConversationSyncUtils.createPointer(c1, SyncedConversationType.newConversation);

    final filtered = SyncProvider.filterFullySyncedConversations(
      conversations: [p1],
      wals: const [],
    );

    expect(filtered, [p1]);
  });
}
