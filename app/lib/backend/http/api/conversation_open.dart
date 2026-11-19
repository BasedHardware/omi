// Opening one conversation by id for a link or a citation; owns telling "gone", "locked" and
// "unreachable" apart, which `getConversationByIdResult` folds into one null (ux-contract §17).

import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
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

Future<ConversationOpen> openConversationById(String conversationId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return const ConversationOpenUnreachable();
  switch (response.statusCode) {
    case 200:
      try {
        return ConversationOpenFound(ServerConversation.fromJson(jsonDecode(response.body) as Map<String, dynamic>));
      } catch (_) {
        return const ConversationOpenUnreachable();
      }
    case 402:
      return const ConversationOpenLocked();
    case 404:
      return const ConversationOpenGone();
    default:
      return const ConversationOpenUnreachable();
  }
}
