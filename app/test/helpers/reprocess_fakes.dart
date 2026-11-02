import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

/// Adapts a fake that answers "the reprocessed conversation, or null on failure" to the typed
/// [ConversationReprocessCall] seam.
ConversationReprocessCall conversationReprocess(
  Future<ServerConversation?> Function(String id, {String? appId, bool requireSpeakerReceipt}) fake,
) {
  return (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async =>
      ReprocessResult.fromConversation(await fake(id, appId: appId, requireSpeakerReceipt: requireSpeakerReceipt));
}
