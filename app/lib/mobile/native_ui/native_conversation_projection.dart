import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';

/// Read-only presentation contract shared by a future Android native renderer.
/// Locked content is stripped before it crosses the platform boundary.
Map<String, Object?> projectNativeConversation(
  ServerConversation conversation, {
  required String title,
  required String timestamp,
  required String lockedTitle,
  required String Function(int index) speaker,
  bool includeDetail = false,
}) {
  final locked = conversation.isLocked;
  return {
    'id': conversation.id,
    'title': locked ? lockedTitle : title,
    'timestamp': timestamp,
    'locked': locked,
    'starred': conversation.starred,
    'status': conversation.status.name,
    if (includeDetail) ...{
      'summary': locked ? '' : ConversationSummarySelection.select(conversation).content,
      'transcript': [
        if (!locked)
          for (var index = 0; index < conversation.transcriptSegments.length; index++)
            {
              // Legacy transcripts can have empty or repeated segment ids. The ordinal is
              // stable within this immutable detail projection and retains every segment.
              'id': '${conversation.id}:$index:${conversation.transcriptSegments[index].id}',
              'speaker': speaker(index),
              'text': conversation.transcriptSegments[index].text,
            },
      ],
      'externalText': locked ? '' : conversation.externalIntegration?.text ?? '',
    },
  };
}
