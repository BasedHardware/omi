// Today's Home, kept whole for the `home-redesign` experiment's control arm (see
// services/experiments/home_redesign.dart). Copied from main as it was before #21711; delete this
// folder once the experiment is decided.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart' show RecordOptionsSheet, PendantListeningSheet;
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_calls_feature.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/home_bottom_bar.dart' show HomeAskAnythingButton;

const _stopGlyphRadius = BorderRadius.all(Radius.circular(4)); // omi-ux-allow: radius-literal -- a glyph

/// Today's Ask bar: main's centred "Ask anything" button (#19854). [onVoice] stays for the caller;
/// the button opens text chat, as on main.
class LegacyHomeChatBar extends StatelessWidget {
  const LegacyHomeChatBar({super.key, required this.onTap, required this.onVoice});

  final VoidCallback onTap;
  final VoidCallback onVoice;

  @override
  Widget build(BuildContext context) => HomeAskAnythingButton(onTap: onTap);
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
      routeToPage(context,
          LiveEpisodePage(topConversationId: captureProvider.topConversationId, initialTab: LiveEpisodeTab.transcript));
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
