import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The header shared by the live, processing and saved conversation pages: the circled back
/// button on the leading edge (the same control as the saved page), and the state as a centred
/// glass pill (canvas Live): a status dot (or a spinner while processing), the state, and the
/// elapsed time while one is given. The state is announced when it changes.
class ConversationStateAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ConversationStateAppBar({
    super.key,
    required this.state,
    this.backKey,
    this.bufferingFor,
    this.sourceLabel,
    this.elapsed,
  });

  /// How long this conversation has been recording, shown after the state ("Listening 02:15").
  final Duration? elapsed;

  /// What is recording ("Pendant", "Phone mic"), shown after the state: "Listening · Pendant".
  final String? sourceLabel;

  /// The state, named from the shared table in `capture_state_labels.dart` so the live page, the
  /// processing page and the conversation list's capture card never give one moment two names.
  final CaptureDisplayState state;

  /// How long audio has been buffered offline, for [CaptureDisplayState.bufferingOffline].
  final Duration? bufferingFor;

  static bool _isLive(CaptureDisplayState state) =>
      state == CaptureDisplayState.listening ||
      state == CaptureDisplayState.capturing ||
      state == CaptureDisplayState.recording;

  /// The transcription-outage sentence is far longer than the one-word states,
  /// so it wraps (smaller, up to three lines) instead of ellipsizing away the
  /// "recording continues" half — the half the reader needs most.
  static bool _isSentenceStatus(CaptureDisplayState state) => state == CaptureDisplayState.transcriptionUnavailable;

  /// Key for the back button, for tests.
  final Key? backKey;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final Widget indicator = switch (state) {
      // v2: Omi thinking is the mark's chase; live is the blue LED, paused or degraded amber.
      CaptureDisplayState.processing => const OmiRingLogo(size: 18, mode: OmiRingMode.chase),
      _ => Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: _isLive(state) ? OmiColors.live : OmiColors.warning,
          ),
        ),
    };
    final sentenceStatus = _isSentenceStatus(state);
    final label = Text(
      // A sentence status keeps all its room; a source adds to a one-word state only.
      sourceLabel == null || sentenceStatus
          ? captureStateLabel(context.l10n, state, bufferingFor: bufferingFor)
          : context.l10n.captureStatusWithSource(
              captureStateLabel(context.l10n, state, bufferingFor: bufferingFor), sourceLabel!),
      style: sentenceStatus
          ? OmiType.footnote.copyWith(fontWeight: FontWeight.w600, height: 1.25)
          : OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
      maxLines: sentenceStatus ? 3 : 1,
      overflow: TextOverflow.ellipsis,
      textAlign: TextAlign.center,
    );
    final time = elapsed;
    final content = Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        ExcludeSemantics(child: indicator),
        const SizedBox(width: OmiSpacing.xs),
        Flexible(child: label),
        if (time != null && !sentenceStatus) ...[
          const SizedBox(width: OmiSpacing.xs),
          Text(
            LiveCaptureCard.formatElapsed(time),
            style: OmiType.subhead.copyWith(
              color: OmiColors.textSecondary,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ],
    );
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: OmiColors.surface0,
      centerTitle: true,
      leading: Center(child: OmiBackButton.circled(key: backKey)),
      title: Semantics(
        liveRegion: true,
        // The long outage sentence wraps on the page; a one-word state sits in the glass pill.
        child: sentenceStatus
            ? content
            : OmiGlass(
                borderRadius: OmiRadius.pillAll,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                  child: content,
                ),
              ),
      ),
    );
  }
}
