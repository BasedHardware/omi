import 'package:flutter/widgets.dart';

import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Something a link, a notification or a citation pointed at that the app could not open.
/// One sentence per kind (ux-contract §17.8), never "Something went wrong".
enum OmiMissingTarget {
  /// A capture card or notification for a recording that has since ended.
  endedRecording,

  /// A memory that was deleted or is not on this phone.
  memory,

  /// A task that was deleted or could not be read.
  task,

  /// A cited conversation that could not be opened (deleted, locked or unreachable).
  conversation,

  /// A linked conversation the server says is deleted (404).
  conversationGone,

  /// A linked conversation that needs a plan to open (402).
  conversationLocked,

  /// A link opened with no connection: never "deleted"; Try Again helps (X14).
  offline;

  String message(BuildContext context) {
    final l10n = context.l10n;
    return switch (this) {
      OmiMissingTarget.endedRecording => l10n.missingTargetEndedRecording,
      OmiMissingTarget.memory => l10n.missingTargetMemory,
      OmiMissingTarget.task => l10n.missingTargetTask,
      OmiMissingTarget.conversation => l10n.missingTargetConversation,
      OmiMissingTarget.conversationGone => l10n.missingTargetConversationGone,
      OmiMissingTarget.conversationLocked => l10n.upgradeToOpenThisOne,
      OmiMissingTarget.offline => l10n.cantConnectRightNow,
    };
  }

  /// Says it where the reader is looking: `OmiFeedback.info`, or an error with Try Again when
  /// trying again can help.
  void show(BuildContext context, {VoidCallback? onRetry}) {
    if (onRetry == null) return OmiFeedback.info(context, message(context));
    OmiFeedback.error(context, message(context), actionLabel: context.l10n.tryAgain, onAction: onRetry);
  }
}
