import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:friend_private/backend/server/message.dart';
import 'package:friend_private/utils/other/notifications.dart';

triggerTranscriptSegmentReceivedEvents(
  List<TranscriptSegment> segments,
  String sessionId, {
  Function(ServerMessage, ServerMemory?)? sendMessageToChat,
}) async {
  webhookOnTranscriptReceivedCall(segments, sessionId).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Developer: On Transcript Received', body: s, notificationId: 10);
  });
  // TODO: restore me, how to trigger from backend
}
