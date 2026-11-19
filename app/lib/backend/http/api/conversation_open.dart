// Opening one conversation by id for a link or a citation; owns telling "gone", "locked" and
// "unreachable" apart, which `getConversationByIdResult` folds into one null (ux-contract §17).

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';

/// What reading a conversation for a link or citation ended in. Only [ConversationOpenFound] opens
/// a page; each other answer has its own message: an offline read is never "deleted".
sealed class ConversationOpen {
  const ConversationOpen();
}

final class ConversationOpenFound extends ConversationOpen {
  const ConversationOpenFound(this.conversation);
  final ServerConversation conversation;
}

/// The server answered 404: the conversation is gone.
final class ConversationOpenGone extends ConversationOpen {
  const ConversationOpenGone();
}

/// The server answered 402: the conversation exists but needs a plan to open.
final class ConversationOpenLocked extends ConversationOpen {
  const ConversationOpenLocked();
}

/// No answer, or one that could not be read: offline, a timeout or a server error. Try Again helps.
final class ConversationOpenUnreachable extends ConversationOpen {
  const ConversationOpenUnreachable();
}

/// Reads through the typed boundary (`ConversationApi.byId`) and keeps its classification: 404 is
/// gone, 402 is locked, and every other failure (transport, server, decode, auth) is unreachable.
Future<ConversationOpen> openConversationById(String conversationId) async {
  final result = await ConversationApi(baseUrl: Env.apiBaseUrl ?? '').byId(conversationId);
  return conversationOpenFrom(result);
}

ConversationOpen conversationOpenFrom(ApiResult<ServerConversation> result) => switch (result) {
      ApiSuccess(:final data) => ConversationOpenFound(data),
      ApiFailure(:final problem) when problem.kind == ApiProblemKind.notFound => const ConversationOpenGone(),
      ApiFailure(:final problem) when problem.kind == ApiProblemKind.paymentRequired => const ConversationOpenLocked(),
      ApiFailure() => const ConversationOpenUnreachable(),
    };
