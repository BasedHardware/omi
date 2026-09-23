import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The states a conversation that is not finished yet can be in, as the reader sees them.
///
/// The live page and the processing page name their state with these, and so does the
/// conversation list's capture card, so one state never has two names (hub audit #25).
// Merge follow-up: lane 1a adds lib/pages/conversations/capture_state_labels.dart with the same
// four labels for the list card; fold this mapping into that file when both land.
enum CaptureDisplayState { recording, paused, reconnecting, processing }

/// The one label for [state]: Recording / Paused / Reconnecting… / Processing.
String captureStateLabel(BuildContext context, CaptureDisplayState state) {
  return switch (state) {
    CaptureDisplayState.recording => context.l10n.recording,
    CaptureDisplayState.paused => context.l10n.paused,
    CaptureDisplayState.reconnecting => context.l10n.reconnecting,
    CaptureDisplayState.processing => context.l10n.processing,
  };
}

/// The header shared by the live, processing and saved conversation pages: the circled back
/// button on the leading edge (the same control as the saved page), and the state as a centred
/// title with a status dot (or a spinner while processing). The state is announced when it
/// changes.
class ConversationStateAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ConversationStateAppBar({super.key, required this.state, this.backKey});

  final CaptureDisplayState state;

  /// Key for the back button, for tests.
  final Key? backKey;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final Widget indicator = switch (state) {
      CaptureDisplayState.processing => const OmiSpinner(size: OmiSpinnerSize.small),
      _ => Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: state == CaptureDisplayState.recording ? OmiColors.danger : OmiColors.warning,
          ),
        ),
    };
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: OmiColors.surface0,
      centerTitle: true,
      leading: Center(child: OmiBackButton.circled(key: backKey)),
      title: Semantics(
        liveRegion: true,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(child: indicator),
            const SizedBox(width: OmiSpacing.xs),
            Flexible(
              child: Text(
                captureStateLabel(context, state),
                style: OmiType.headline,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
