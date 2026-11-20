import 'package:flutter/widgets.dart';

import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

// The one Share flow for a conversation (V1, V5): consent, make it shared, open the system sheet,
// and put it back to private when the sheet is dismissed or fails. It owns the rule that the
// message the reader sees always matches the conversation's real visibility (ux-contract §17).

/// How sharing a conversation ended. The message always matches its real visibility.
enum ShareFlowEnd {
  /// The share sheet was used; the conversation is shared.
  shared,

  /// The reader said no at the consent step; nothing changed.
  cancelled,

  /// The reader closed the share sheet; a conversation that was private is private again.
  dismissed,

  /// Nothing was shared and the conversation is as it was (private when it was private).
  failed,

  /// Nothing was shared, but the conversation could not be made private again: it is public.
  stillPublic,
}

/// Share and the visibility menu's "Shared" are one path (ux-contract §17.7): ask first when the
/// conversation is private ("Anyone with the link can view"), make it shared, open the share sheet,
/// and make it private again if the sheet was dismissed or failed. A revert that fails is
/// [ShareFlowEnd.stillPublic], never "not shared".
Future<ShareFlowEnd> runConversationShare({
  required bool wasPrivate,
  required Future<bool> Function() confirm,
  required Future<bool> Function(ConversationVisibility visibility) setVisibility,
  required void Function(ConversationVisibility visibility) onVisibility,
  required Future<ShareResultStatus> Function() openSheet,
}) async {
  if (wasPrivate) {
    if (!await confirm()) return ShareFlowEnd.cancelled;
    if (!await _set(setVisibility, ConversationVisibility.shared)) return ShareFlowEnd.failed;
    onVisibility(ConversationVisibility.shared);
  }

  Future<ShareFlowEnd> revert(ShareFlowEnd ifReverted) async {
    if (!wasPrivate) return ifReverted;
    if (!await _set(setVisibility, ConversationVisibility.private_)) return ShareFlowEnd.stillPublic;
    onVisibility(ConversationVisibility.private_);
    return ifReverted;
  }

  final ShareResultStatus status;
  try {
    status = await openSheet();
  } catch (_) {
    return revert(ShareFlowEnd.failed);
  }
  if (status == ShareResultStatus.dismissed) return revert(ShareFlowEnd.dismissed);
  return ShareFlowEnd.shared;
}

Future<bool> _set(Future<bool> Function(ConversationVisibility) setVisibility, ConversationVisibility target) async {
  try {
    return await setVisibility(target);
  } catch (_) {
    return false;
  }
}

/// Says how sharing ended when the reader needs to know: a failure, or a conversation left public
/// (with Make Private, which tries again).
void showShareFlowEnd(BuildContext context, ShareFlowEnd end, {required VoidCallback makePrivate}) {
  final l10n = context.l10n;
  switch (end) {
    case ShareFlowEnd.failed:
      OmiFeedback.error(context, l10n.conversationUrlNotShared);
    case ShareFlowEnd.stillPublic:
      OmiFeedback.error(context, l10n.conversationStillPublic, actionLabel: l10n.makePrivate, onAction: makePrivate);
    case ShareFlowEnd.shared || ShareFlowEnd.cancelled || ShareFlowEnd.dismissed:
      break;
  }
}
