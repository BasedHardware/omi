import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The header shared by the live, processing and saved conversation pages: the circled back
/// button on the leading edge (the same control as the saved page), and the state as a centred
/// title with a status dot (or a spinner while processing). The state is announced when it
/// changes. With a [title], the page's name is the title and the state row sits under it in
/// smaller type (the live page), followed by the session clock while the state is live.
class ConversationStateAppBar extends StatelessWidget implements PreferredSizeWidget {
  const ConversationStateAppBar({
    super.key,
    required this.state,
    this.backKey,
    this.bufferingFor,
    this.sourceLabel,
    this.showStatus = true,
    this.title,
    this.startedAt,
  });

  /// What is recording ("Pendant", "Phone mic"), shown after the state: "Listening · Pendant".
  final String? sourceLabel;
  final bool showStatus;

  /// The page's name above the state row (the live page). Null: the state is the title.
  final String? title;

  /// When the live recording started: a clock after the state row while the state is live. It
  /// sits outside the announced state, so it never talks over the words before it.
  final DateTime? startedAt;

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
    final sentenceStatus = _isSentenceStatus(state);
    final titled = title != null;
    // Under a title the state is a secondary line; on its own it is the headline.
    final TextStyle statusStyle = sentenceStatus
        ? OmiType.footnote.copyWith(fontWeight: FontWeight.w600, height: 1.25)
        : titled
            ? OmiType.footnote.copyWith(color: OmiColors.textSecondary)
            : sourceLabel == null
                ? OmiType.headline
                : OmiType.headline.copyWith(height: 1.15);
    Widget status = Semantics(
      liveRegion: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          ExcludeSemantics(child: indicator),
          const SizedBox(width: OmiSpacing.xs),
          Flexible(
            child: Text(
              // A sentence status keeps all its room; a source adds to a one-word state only.
              sourceLabel == null || sentenceStatus
                  ? captureStateLabel(context.l10n, state, bufferingFor: bufferingFor)
                  : context.l10n.captureStatusWithSource(
                      captureStateLabel(context.l10n, state, bufferingFor: bufferingFor), sourceLabel!),
              style: statusStyle,
              maxLines: sentenceStatus ? (titled ? 2 : 3) : (sourceLabel == null || titled ? 1 : 2),
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
    if (titled && startedAt != null && _isLive(state)) {
      status = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Flexible(child: status),
          _SessionClock(startedAt: startedAt!, style: statusStyle),
        ],
      );
    }
    final Widget heading = !showStatus
        ? Text(sourceLabel ?? '',
            style: titled ? OmiType.footnote.copyWith(color: OmiColors.textSecondary) : OmiType.headline)
        : status;
    return AppBar(
      automaticallyImplyLeading: false,
      backgroundColor: OmiColors.surface0,
      centerTitle: true,
      leading: Center(child: OmiBackButton.circled(key: backKey)),
      title: !titled
          ? heading
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(title!, style: OmiType.headline, maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                heading,
              ],
            ),
    );
  }
}

/// How long the recording has run, ticking once a second: m:ss, and h:mm:ss past the hour.
class _SessionClock extends StatefulWidget {
  const _SessionClock({required this.startedAt, required this.style});

  final DateTime startedAt;
  final TextStyle style;

  @override
  State<_SessionClock> createState() => _SessionClockState();
}

class _SessionClockState extends State<_SessionClock> {
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final seconds = DateTime.now().difference(widget.startedAt).inSeconds;
    return Text(
      ' · ${OmiDuration.offset(seconds < 0 ? 0 : seconds)}',
      style: widget.style.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
      maxLines: 1,
    );
  }
}
