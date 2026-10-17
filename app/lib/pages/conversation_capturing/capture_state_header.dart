import 'package:flutter/material.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The title [ConversationStateAppBar] shows, as one string: the source alone without a status, a
/// sentence status alone, otherwise the state with its source ("Listening · Pendant").
String conversationStateTitle(
  AppLocalizations l10n,
  CaptureDisplayState state, {
  Duration? bufferingFor,
  String? sourceLabel,
  bool showStatus = true,
}) {
  if (!showStatus) return sourceLabel ?? '';
  final label = captureStateLabel(l10n, state, bufferingFor: bufferingFor);
  // A sentence status keeps all its room; a source adds to a one-word state only.
  return sourceLabel == null || ConversationStateAppBar.isSentenceStatus(state)
      ? label
      : l10n.captureStatusWithSource(label, sourceLabel);
}

/// The header shared by the live, processing and saved conversation pages: the circled back
/// button on the leading edge (the same control as the saved page), and the state as a centred
/// title with a status dot (or a spinner while processing). The state is announced when it
/// changes.
class ConversationStateAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ConversationStateAppBar(
      {super.key, required this.state, this.backKey, this.bufferingFor, this.sourceLabel, this.showStatus = true});

  /// What is recording ("Pendant", "Phone mic"), shown after the state: "Listening · Pendant".
  final String? sourceLabel;
  final bool showStatus;

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
  /// "recording continues" half — the half the reader needs most. Public so a header that cannot
  /// wrap its title (the native reader's) can show the sentence in full elsewhere.
  static bool isSentenceStatus(CaptureDisplayState state) => state == CaptureDisplayState.transcriptionUnavailable;

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
    final sentenceStatus = isSentenceStatus(state);
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: OmiColors.surface0,
      centerTitle: true,
      leading: Center(child: OmiBackButton.circled(key: backKey)),
      title: !showStatus
          ? Text(sourceLabel ?? '', style: OmiType.headline)
          : Semantics(
              liveRegion: true,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  ExcludeSemantics(child: indicator),
                  const SizedBox(width: OmiSpacing.xs),
                  Flexible(
                    child: Text(
                      conversationStateTitle(context.l10n, state, bufferingFor: bufferingFor, sourceLabel: sourceLabel),
                      style: sentenceStatus
                          ? OmiType.footnote.copyWith(fontWeight: FontWeight.w600, height: 1.25)
                          : sourceLabel == null
                              ? OmiType.headline
                              : OmiType.headline.copyWith(height: 1.15),
                      maxLines: sentenceStatus ? 3 : (sourceLabel == null ? 1 : 2),
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
