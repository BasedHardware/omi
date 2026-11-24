import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/finish_capture.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/services/capture/finish_outcome.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

/// Home's bottom row while this phone records a live conversation: one bar in place of the
/// Ask Omi bar and the round record button (David, 2026-11-16).
///
/// Starting a phone recording keeps the reader on Home; this bar is the confirmation. For the
/// first [undoWindow] it offers Undo, which discards the recording (no row, nothing processed),
/// so an accidental tap costs nothing. After that it offers Wrap Up, the same finish as the live
/// page's. Tapping the rest of the bar opens the live transcript.
class HomeRecordingBar extends StatefulWidget {
  const HomeRecordingBar({super.key, this.now = DateTime.now});

  /// How long Undo stays on the bar before it turns into Wrap Up.
  static const Duration undoWindow = Duration(seconds: 5);

  /// The clock; tests pass a fixed one.
  final DateTime Function() now;

  /// Whether the bar replaces Home's bottom row: a live (not Transcribe Later) recording owned by
  /// this phone, from when its start commits until it stops.
  static bool showsFor(CaptureProvider capture) =>
      capture.liveCaptureSource == 'phone' && !capture.isPhoneMicBatchRecording;

  @override
  State<HomeRecordingBar> createState() => _HomeRecordingBarState();
}

class _HomeRecordingBarState extends State<HomeRecordingBar> {
  Timer? _tick;
  bool _busy = false;

  /// When the bar appeared; it bounds the Undo window while the mic has not reported a start time.
  late final DateTime _shownAt;

  @override
  void initState() {
    super.initState();
    _shownAt = widget.now();
    // The elapsed time and the Undo → Wrap Up switch both move on whole seconds.
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _undo(CaptureProvider capture) async {
    if (_busy) return;
    setState(() => _busy = true);
    OmiHaptics.medium();
    // The bar leaves the tree as soon as the recording stops, so the confirmation is built now and
    // shown by the messenger, which outlives it.
    final messenger = ScaffoldMessenger.maybeOf(context);
    final l10n = context.l10n;
    final discarded = OmiFeedback.buildSnackBar(
      context,
      l10n.recordingDiscarded,
      kind: OmiFeedbackKind.confirm,
      duration: OmiFeedbackTiming.confirm,
    );
    try {
      // The recording may have ended on its own since the last frame; then there is nothing to confirm.
      if (!await capture.discardPhoneRecording()) return;
      // Pairs with phoneMicRecordingStarted; the recording's lifecycle telemetry says it was
      // discarded (reason user_discarded).
      PlatformManager.instance.analytics.phoneMicRecordingStopped();
      if (messenger != null && messenger.mounted) {
        messenger
          ..hideCurrentSnackBar()
          ..showSnackBar(discarded);
      }
    } catch (_) {
      if (mounted) OmiFeedback.error(context, l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Wrap Up is Finish from Home: the same path and the same outcome (ux-contract §17.7). The bar
  /// leaves the tree once the recording stops, so the outcome is shown from Home's context.
  Future<void> _wrapUp(CaptureProvider capture) async {
    if (_busy) return;
    setState(() => _busy = true);
    OmiHaptics.medium();
    final home = Navigator.of(context).context;
    final outcome = await finishLiveCapture(context, capture, episodes: context.read<EpisodeProvider?>());
    if (outcome is! FinishFailed) PlatformManager.instance.analytics.phoneMicRecordingStopped();
    if (mounted) setState(() => _busy = false);
    if (!home.mounted) return;
    presentFinishOutcome(home, outcome, entry: FinishEntry.home, onRetry: () => retryFinishFromHome(home, capture));
  }

  void _open(CaptureProvider capture) {
    OmiHaptics.selection();
    routeToPage(
      context,
      LiveEpisodePage(topConversationId: capture.topConversationId, initialTab: LiveEpisodeTab.transcript),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final capture = context.watch<CaptureProvider>();
    final now = widget.now();
    final startedAt = capture.liveCaptureStartedAt;
    final elapsed = startedAt == null ? Duration.zero : now.difference(startedAt);
    // Undo until the recording has run for the whole window. Before the mic reports a start time
    // the clock reads 0:00, and the window counts from when the bar appeared instead.
    final canUndo = (startedAt == null ? now.difference(_shownAt) : elapsed) < HomeRecordingBar.undoWindow;
    final paused = capture.isPhoneMicPaused ||
        capture.recordingState == RecordingState.pause ||
        capture.recordingState == RecordingState.interrupted;
    final clock = LiveCaptureCard.formatElapsed(elapsed.isNegative ? Duration.zero : elapsed);
    final detail = paused ? '$clock · ${l10n.paused}' : clock;

    final body = Semantics(
      button: true,
      label: '${l10n.recordingWithYourPhone}, $detail',
      hint: l10n.episodeOpenTranscript,
      // excludeSemantics drops the GestureDetector's own tap action, so the node carries it.
      onTap: () => _open(capture),
      excludeSemantics: true,
      child: GestureDetector(
        key: const ValueKey('home_recording_bar_open'),
        behavior: HitTestBehavior.opaque,
        onTap: () => _open(capture),
        child: Row(
          children: [
            // The same mark as Home's live card: red while this phone records, grey when paused.
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: paused ? OmiColors.textTertiary : OmiColors.danger,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    l10n.recordingWithYourPhone,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 1),
                  Text(
                    detail,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(
                      color: OmiColors.textSecondary,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );

    final action = canUndo
        ? OmiButton.secondary(
            key: const ValueKey('home_recording_bar_undo'),
            label: l10n.undo,
            size: OmiButtonSize.compact,
            pill: true,
            leading: const Icon(Icons.undo_rounded, size: 18),
            onPressed: _busy ? null : () => _undo(capture),
          )
        : OmiButton(
            key: const ValueKey('home_recording_bar_wrap_up'),
            label: l10n.wrapUp,
            size: OmiButtonSize.compact,
            pill: true,
            onPressed: _busy ? null : () => _wrapUp(capture),
          );

    return Container(
      key: const ValueKey('home_recording_bar'),
      height: kHomeChatBarHeight,
      padding: const EdgeInsetsDirectional.only(start: OmiSpacing.lg, end: OmiSpacing.sm),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: OmiColors.border, width: 1),
      ),
      child: Row(
        children: [
          Expanded(child: body),
          const SizedBox(width: OmiSpacing.xs),
          action,
        ],
      ),
    );
  }
}
