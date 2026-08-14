import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/widgets/conversations_group_widget.dart';

void main() {
  test('conversation group entries preserve newest-first ordering across sources', () {
    final olderConversation = _conversation('older', DateTime.utc(2026, 8, 10, 9));
    final newerRecording = _recording('newer.bin', DateTime.utc(2026, 8, 10, 10));
    final entries = buildConversationGroupEntries(conversations: [olderConversation], recordings: [newerRecording]);

    expect(entries.map((entry) => entry.conversation?.id ?? entry.recording?.id), ['newer.bin', 'older']);
  });
}

ServerConversation _conversation(String id, DateTime createdAt) =>
    ServerConversation(id: id, createdAt: createdAt, structured: Structured('Title', 'Overview'));

LocalRecording _recording(String fileName, DateTime startedAt) => LocalRecording(
      fileName: fileName,
      filePath: '/tmp/$fileName',
      timerStart: startedAt.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      frameSize: 160,
      sizeBytes: 1024,
      seconds: 1,
      state: LocalRecordingState.pending,
    );
