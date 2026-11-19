// Whether a conversation is still being recorded, and the actions that wait until it ends; owns the
// one predicate Home rows and the conversation page share (X11).

import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// True while [conversation] is still being recorded: a v3 account and a live tile. Capture still
/// writes it, so it is not deleted, reprocessed, shared or edited until it ends.
bool conversationIsLive(ServerConversation conversation, {required bool v3}) =>
    v3 && conversation.v3?.tileState == ConversationTileState.live;

/// [conversationIsLive] for the account in [context].
bool conversationIsLiveIn(BuildContext context, ServerConversation conversation) =>
    conversationIsLive(conversation, v3: context.read<ConversationsV3Provider?>()?.v3 ?? false);

/// Conversation actions that change, share or remove it.
const liveRefusedActions = {'reprocess', 'rename', 'move_to_folder', 'visibility', 'delete', 'link_event', 'share'};

/// When [action] would change a live conversation, says why it waits and returns true; the caller
/// does nothing. A control never does nothing in silence (ux-contract §17).
bool refuseWhileLive(BuildContext context, ServerConversation conversation, String action) {
  if (!liveRefusedActions.contains(action) || !conversationIsLiveIn(context, conversation)) return false;
  OmiFeedback.info(context, context.l10n.conversationLiveNoEdits);
  return true;
}
