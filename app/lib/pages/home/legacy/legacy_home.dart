// Today's Home, kept whole for the `home-redesign` experiment's control arm (see
// services/experiments/home_redesign.dart). Copied from main as it was before #21711; delete this
// folder once the experiment is decided.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart' show RecordOptionsSheet, PendantListeningSheet;
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_calls_feature.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/processing_timeout.dart';
import 'package:omi/widgets/capture_sources.dart';

/// Today's chat bar height (the redesign's bottom controls are 56).
const double _legacyChatBarHeight = 62;

const _stopGlyphRadius = BorderRadius.all(Radius.circular(4)); // omi-ux-allow: radius-literal -- a glyph

/// Today's Ask Omi bar: the full-width chat field with a mic at its end.
class LegacyHomeChatBar extends StatelessWidget {
  const LegacyHomeChatBar({super.key, required this.onTap, required this.onVoice});

  final VoidCallback onTap;
  final VoidCallback onVoice;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      label: context.l10n.askOmi,
      onTap: onTap,
      child: GestureDetector(
        key: const ValueKey('home_ask_omi_bar'),
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: _legacyChatBarHeight,
          decoration: BoxDecoration(
            color: OmiColors.surface1,
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: OmiColors.border, width: 1),
          ),
          child: Row(
            children: [
              const SizedBox(width: 18),
              Expanded(
                child: ExcludeSemantics(
                  child: Text(
                    context.l10n.askOmi,
                    style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              GestureDetector(
                // The mic sits inside the chat bar's own tap target, so a near miss
                // does not do nothing: it opens text chat instead of voice. Own the
                // bar's full height and its rounded end, not just the 42pt circle.
                behavior: HitTestBehavior.opaque,
                onTap: () => onVoice(),
                child: Semantics(
                  container: true,
                  button: true,
                  label: context.l10n.voiceMode,
                  child: Container(
                    height: _legacyChatBarHeight,
                    padding: const EdgeInsets.only(left: 8, right: 6),
                    alignment: Alignment.center,
                    child: Container(
                      width: 42,
                      height: 42,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
                      child: FaIcon(FontAwesomeIcons.microphone, size: 15, color: OmiColors.onAccent),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Circular phone-mic record button shown to the right of the home chat bar.
/// Tap starts/stops recording; long-press opens the record options sheet (phone call). The options
/// are announced as the long-press action, and a one-time tip points them out after the first
/// recording.
class LegacyHomeRecordButton extends StatefulWidget {
  const LegacyHomeRecordButton({super.key});

  @override
  State<LegacyHomeRecordButton> createState() => _LegacyHomeRecordButtonState();
}

class _LegacyHomeRecordButtonState extends State<LegacyHomeRecordButton> {
  static const _optionsTipKey = 'v2/homeRecordOptionsTipShown';

  void _showRecordOptions(BuildContext context) {
    OmiHaptics.light();
    SharedPreferencesUtil().saveBool(_optionsTipKey, true);
    showOmiSheet<void>(
      context: context,
      title: context.l10n.recordWith,
      builder: (sheetContext) => RecordOptionsSheet(
        onPickPhoneMic: () {
          Navigator.pop(sheetContext);
          _startRecording(context);
        },
        onPickPhoneCall: () {
          Navigator.pop(sheetContext);
          if (!context.mounted) return;
          routeToPage(context, const PhoneCallsPage());
        },
      ),
    );
  }

  /// Once, after the first recording stops: say that holding the button offers more ways to record.
  void _maybeShowOptionsTip(BuildContext context) {
    if (!PhoneCallsFeature.visible) return;
    final prefs = SharedPreferencesUtil();
    if (prefs.getBool(_optionsTipKey)) return;
    prefs.saveBool(_optionsTipKey, true);
    OmiFeedback.info(context, context.l10n.recordOptionsTip);
  }

  static bool _callInProgress(BuildContext context) {
    final state = context.read<PhoneCallProvider>().callState;
    return state == PhoneCallState.connecting || state == PhoneCallState.ringing || state == PhoneCallState.active;
  }

  /// The pendant is recording (or paused) in realtime mode: explain, and let the user choose.
  /// A Transcribe Later pendant is excluded — its capture can't be taken over at all, so it
  /// falls through to the refusal feedback rather than offering a choice that would fail.
  static bool _pendantHasCapture(CaptureProvider capture) {
    final source = capture.liveCaptureSource;
    return source != null &&
        source != 'phone' &&
        !SharedPreferencesUtil().batchModeEnabled &&
        !capture.isPendantBatchRecording;
  }

  void _showPendantListening(BuildContext context) {
    OmiHaptics.light();
    showOmiSheet<void>(
      context: context,
      title: context.read<CaptureProvider>().pendantCaptureVerified
          ? context.l10n.pendantIsListeningTitle
          : CaptureSources.label(context, 'omi'),
      builder: (sheetContext) => PendantListeningSheet(
        onRecordWithPhone: () {
          Navigator.pop(sheetContext);
          _startPhoneRecording(context);
        },
        onPhoneCall: PhoneCallsFeature.visible
            ? () {
                Navigator.pop(sheetContext);
                if (context.mounted) routeToPage(context, const PhoneCallsPage());
              }
            : null,
        onKeepPendant: () => Navigator.pop(sheetContext),
      ),
    );
  }

  Future<void> _startRecording(BuildContext context) async {
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.recordingState == RecordingState.initialising) return;
    // An Omi call owns the capture while it runs: the button opens the call, never a recording.
    if (_callInProgress(context)) {
      routeToPage(context, const ActiveCallPage());
      return;
    }
    if (_pendantHasCapture(captureProvider) && !captureProvider.isPhoneMicPaused) {
      _showPendantListening(context);
      return;
    }
    await _startPhoneRecording(context);
  }

  Future<void> _startPhoneRecording(BuildContext context) async {
    final captureProvider = context.read<CaptureProvider>();
    OmiHaptics.medium();
    if (captureProvider.recordingState == RecordingState.record || captureProvider.isPhoneMicPaused) {
      // The phone recording is this button's own: finish it (processed, except Transcribe Later,
      // whose local file is finalized on stop), then any pendant it paused resumes.
      await captureProvider.finishCapture();
      PlatformManager.instance.analytics.phoneMicRecordingStopped();
      if (context.mounted) _maybeShowOptionsTip(context);
      return;
    }
    if (captureProvider.isPendantBatchRecording) {
      if (context.mounted) {
        OmiFeedback.info(context, context.l10n.phoneRecordingBlockedByPendantBatch);
      }
      return;
    }
    try {
      await captureProvider.streamRecording();
    } catch (_) {
      if (context.mounted) {
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
      return;
    }
    if (captureProvider.liveCaptureSource != 'phone') return;
    PlatformManager.instance.analytics.phoneMicRecordingStarted();
    // Phone-mic Transcribe Later (batch) has no live transcript — its surface is the
    // conversations-list batch card, so skip the capturing page (same as BLE batch).
    if (captureProvider.isPhoneMicBatchRecording) {
      if (SharedPreferencesUtil().phoneBatchAuto && context.mounted) {
        OmiFeedback.info(context, context.l10n.phoneMicOfflineFallbackMessage);
      }
      return;
    }
    if (context.mounted) {
      routeToPage(context, ConversationCapturingPage(topConversationId: captureProvider.topConversationId));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, _) {
        // The phone recording is this button's own (live or paused); anything else is idle here.
        final isRecording = captureProvider.recordingState == RecordingState.record || captureProvider.isPhoneMicPaused;
        final isInitialising = captureProvider.recordingState == RecordingState.initialising;
        // The options sheet only adds a phone call; with calls hidden there is nothing else to offer.
        final canShowOptions = PhoneCallsFeature.visible && !isRecording && !isInitialising;
        final l10n = context.l10n;
        final circle = Semantics(
          button: true,
          label: isRecording ? l10n.stopRecording : l10n.startRecording,
          enabled: !isInitialising,
          // The child's gestures are excluded below, so the actions (tap, and long-press for the
          // record options) are declared here where assistive tech can reach them.
          onTap: isInitialising ? null : () => _startRecording(context),
          onLongPress: canShowOptions ? () => _showRecordOptions(context) : null,
          onLongPressHint: canShowOptions ? l10n.moreOptions : null,
          excludeSemantics: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => _startRecording(context),
            onLongPress: canShowOptions ? () => _showRecordOptions(context) : null,
            // "Record with this phone": a neutral circle with a white dot, a stop square while the
            // phone records. The ⌄ badge opens the other ways to record.
            child: Container(
              width: 62,
              height: 62,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: OmiColors.surface1,
                shape: BoxShape.circle,
                border: Border.all(color: OmiColors.border, width: 1),
              ),
              child: isRecording
                  ? Container(
                      width: 18,
                      height: 18,
                      decoration: BoxDecoration(
                        color: OmiColors.textPrimary,
                        borderRadius: _stopGlyphRadius,
                      ),
                    )
                  : isInitialising
                      ? const OmiSpinner(size: OmiSpinnerSize.small)
                      : Container(
                          width: 20,
                          height: 20,
                          decoration: BoxDecoration(color: OmiColors.textPrimary, shape: BoxShape.circle),
                        ),
            ),
          ),
        );
        // The badge is its own control (and its own accessibility node) beside the circle's.
        return SizedBox(
          width: 62,
          height: 62,
          child: Stack(clipBehavior: Clip.none, children: [
            circle,
            if (canShowOptions)
              Positioned(
                right: 0,
                bottom: 0,
                child: Semantics(
                  button: true,
                  label: l10n.moreWaysToRecord,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => _showRecordOptions(context),
                    // A 30pt hit area around the 22pt badge, inside the button's 62pt box (a Stack
                    // does not hit-test outside its bounds, and 44pt would cover the circle's
                    // centre). Screen readers also get the options as the circle's long-press action.
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: Container(
                        width: 22,
                        height: 22,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: OmiColors.surface3,
                          shape: BoxShape.circle,
                          border: Border.all(color: OmiColors.surface0, width: 2),
                        ),
                        child: Icon(Icons.keyboard_arrow_down_rounded, size: 16, color: OmiColors.textPrimary),
                      ),
                    ),
                  ),
                ),
              ),
          ]),
        );
      },
    );
  }
}

// PROCESSING CONVERSATION

class LegacyProcessingConversationWidget extends StatefulWidget {
  final ServerConversation conversation;

  /// Optional clock override for tests.
  final DateTime Function()? now;

  /// Optional reprocess override for tests.
  final Future<ServerConversation?> Function(String conversationId)? reprocess;

  const LegacyProcessingConversationWidget({super.key, required this.conversation, this.now, this.reprocess});

  @override
  State<LegacyProcessingConversationWidget> createState() => _LegacyProcessingConversationWidgetState();
}

class _LegacyProcessingConversationWidgetState extends State<LegacyProcessingConversationWidget> {
  Timer? _timeoutTicker;
  bool _timedOut = false;
  bool _retrying = false;

  /// Wall-clock when processing is treated as having started for the timeout.
  /// Prefer [ServerConversation.finishedAt] (capture end ≈ processing start);
  /// fall back to first paint / retry so long recordings are not instantly flagged.
  late DateTime _processingStartedAt;

  DateTime get _now => widget.now?.call() ?? DateTime.now();

  DateTime _resolveProcessingStartedAt() {
    return widget.conversation.finishedAt ?? _now;
  }

  @override
  void initState() {
    super.initState();
    _processingStartedAt = _resolveProcessingStartedAt();
    _refreshTimeout();
    _timeoutTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      _refreshTimeout();
    });
  }

  @override
  void didUpdateWidget(LegacyProcessingConversationWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversation.id != widget.conversation.id) {
      _processingStartedAt = _resolveProcessingStartedAt();
      _refreshTimeout();
      return;
    }
    final nextFinishedAt = widget.conversation.finishedAt;
    if (nextFinishedAt != null && nextFinishedAt != oldWidget.conversation.finishedAt) {
      _processingStartedAt = nextFinishedAt;
      _refreshTimeout();
    }
  }

  @override
  void dispose() {
    _timeoutTicker?.cancel();
    super.dispose();
  }

  void _refreshTimeout() {
    final timedOut = isConversationProcessingTimedOut(
      conversationId: widget.conversation.id,
      processingStartedAt: _processingStartedAt,
      now: _now,
    );
    if (timedOut != _timedOut) {
      setState(() => _timedOut = timedOut);
    }
  }

  Future<void> _onRetry() async {
    if (_retrying || widget.conversation.id == '0') return;
    setState(() => _retrying = true);
    try {
      final reprocess = widget.reprocess ?? reProcessConversationServer;
      final updated = await reprocess(widget.conversation.id);
      if (!mounted) return;
      final provider = context.read<ConversationProvider>();
      if (updated == null) {
        AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
        return;
      }
      if (updated.status == ConversationStatus.processing || updated.status == ConversationStatus.merging) {
        // Fresh attempt — give the new processing pass another full timeout window.
        _processingStartedAt = _now;
        _timedOut = false;
        provider.addProcessingConversation(updated, freshProcessingAttempt: true);
      } else {
        try {
          ClientTelemetry.instance.noteProcessingRowLeft(
            id: widget.conversation.id,
            lifecycleOk: true,
            lifecycleStatus: updated.status.name,
          );
        } catch (_) {}
        provider.removeProcessingConversation(widget.conversation.id);
        provider.upsertConversation(updated);
      }
    } catch (_) {
      if (!mounted) return;
      AppSnackbar.showSnackbarError(context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _retrying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        routeToPage(context, ProcessingConversationPage(conversation: widget.conversation));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(24.0)),
          // Static skeleton - no animation to save CPU/battery
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header row
                Row(
                  children: [
                    // Icon placeholder
                    Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: OmiColors.surface2,
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // Processing label
                    Container(
                      decoration: BoxDecoration(
                        color: OmiColors.categorySurface,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: Text(
                        captureStateLabel(context.l10n, CaptureDisplayState.processing),
                        style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                      ),
                    ),
                    const Spacer(),
                    // The real start time, not a placeholder bar (hub audit #25).
                    Text(
                      OmiDateFormat.of(context).time(widget.conversation.startedAt ?? widget.conversation.createdAt),
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                // Title placeholder
                Container(
                  width: double.maxFinite,
                  height: 16,
                  decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: BorderRadius.circular(4)),
                ),
                if (_timedOut) ...[
                  const SizedBox(height: 12),
                  Text(
                    context.l10n.processingTakingLonger,
                    style: TextStyle(color: OmiColors.textTertiary, fontSize: 13, height: 1.3),
                  ),
                  const SizedBox(height: 10),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: GestureDetector(
                      onTap: () {}, // absorb so the card's open-on-tap does not fire
                      child: TextButton(
                        key: const Key('processing_conversation_retry_button'),
                        onPressed: _retrying ? null : _onRetry,
                        style: TextButton.styleFrom(
                          foregroundColor: OmiColors.textPrimary,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          minimumSize: const Size(44, 44),
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        child: _retrying ? const OmiSpinner(size: OmiSpinnerSize.small) : Text(context.l10n.tryAgain),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
