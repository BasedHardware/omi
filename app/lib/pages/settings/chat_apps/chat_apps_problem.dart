import 'package:flutter/material.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Why a chat-app action failed, in the reader's terms.
enum ChatAppsProblem {
  /// No connection: try again once online.
  offline,

  /// The backend refused (403): outside the rollout, plan changed, or the channel is off.
  unavailable,

  /// Too many attempts in a short time.
  rateLimited,

  /// The channel is full (409); the backend put the account on its waitlist. Not an error.
  waitlisted,

  /// Anything else; trying again may work.
  failed;

  static ChatAppsProblem fromApi(ApiProblem problem) => switch (problem.kind) {
        _ when isSeatCapProblem(problem) => waitlisted,
        ApiProblemKind.transport => offline,
        ApiProblemKind.forbidden || ApiProblemKind.paymentRequired || ApiProblemKind.notFound => unavailable,
        ApiProblemKind.rateLimited => rateLimited,
        _ => failed,
      };

  /// Retrying cannot help until something changes outside this screen.
  bool get blocksRetry => this == unavailable || this == waitlisted;

  String message(BuildContext context) {
    final l10n = context.l10n;
    return switch (this) {
      offline => l10n.chatAppsProblemOffline,
      unavailable => l10n.chatAppsProblemUnavailable,
      rateLimited => l10n.chatAppsProblemRateLimited,
      waitlisted => l10n.chatAppsWaitlistJoined,
      failed => l10n.chatAppsProblemFailed,
    };
  }
}

/// An inline, announced error line inside a sheet.
class ChatAppsProblemLine extends StatelessWidget {
  const ChatAppsProblemLine(this.problem, {super.key});

  final ChatAppsProblem problem;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Row(
        key: ValueKey('chat_apps_problem_${problem.name}'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(child: Icon(Icons.error_outline_rounded, size: 18, color: OmiColors.danger)),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(
              child: Text(problem.message(context), style: OmiType.footnote.copyWith(color: OmiColors.textPrimary))),
        ],
      ),
    );
  }
}

/// Closes a connect sheet after minting answered 409: the person is on the channel's waitlist,
/// which the page row now shows. Confirms it instead of showing an error.
void closeConnectSheetOnWaitlist(BuildContext context) {
  OmiFeedback.confirm(context, context.l10n.chatAppsWaitlistJoined);
  Navigator.of(context).pop();
}
