import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The header shared by the live, processing and saved conversation pages: the circled back
/// button on the leading edge (the same control as the saved page), and the state as a centred
/// title with a status dot (or a spinner while processing). The state is announced when it
/// changes.
class ConversationStateAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ConversationStateAppBar({super.key, required this.state, this.backKey, this.bufferingFor});

  /// The state, named from the shared table in `capture_state_labels.dart` so the live page, the
  /// processing page and the conversation list's capture card never give one moment two names.
  final CaptureDisplayState state;

  /// How long audio has been buffered offline, for [CaptureDisplayState.bufferingOffline].
  final Duration? bufferingFor;

  static bool _isLive(CaptureDisplayState state) =>
      state == CaptureDisplayState.listening ||
      state == CaptureDisplayState.capturing ||
      state == CaptureDisplayState.recording;

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
            color: _isLive(state) ? OmiColors.danger : OmiColors.warning,
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
                captureStateLabel(context.l10n, state, bufferingFor: bufferingFor),
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
