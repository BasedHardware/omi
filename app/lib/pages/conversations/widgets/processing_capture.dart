import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/processing_timeout.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/ui/ui.dart';

class ConversationCaptureWidget extends StatefulWidget {
  const ConversationCaptureWidget({super.key, this.showsCall = false});

  /// Home shows an Omi call on this card; the Conversations tab has its own call banner.
  final bool showsCall;

  @override
  State<ConversationCaptureWidget> createState() => _ConversationCaptureWidgetState();
}

class _ConversationCaptureWidgetState extends State<ConversationCaptureWidget> {
  Timer? _offlineTicker;
  int _offlineTick = 0;

  @override
  void initState() {
    super.initState();
    // Drive the "captured so far" timer on the offline capture card. Cheap no-op
    // (just a null check) whenever an offline recording session isn't active.
    _offlineTicker = Timer.periodic(const Duration(seconds: 1), (_) async {
      if (!mounted) return;
      final provider = context.read<CaptureProvider>();
      if (provider.offlineRecordingStartedAt != null ||
          provider.customSttBufferingDuration != null ||
          provider.liveCaptureStartedAt != null ||
          (widget.showsCall && context.read<PhoneCallProvider>().callState == PhoneCallState.active)) {
        setState(() {}); // the elapsed time on the card
      }
      _offlineTick++;
      // The pendant card is fed by prefs the native drain engine writes; reload
      // periodically because the Dart prefs cache doesn't see native writes.
      if (_offlineTick % 10 == 0 &&
          SharedPreferencesUtil().batchModeEnabled &&
          provider.recordingDevice?.type == DeviceType.limitless) {
        await SharedPreferencesUtil.reload();
        if (mounted) setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _offlineTicker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // During an Omi call the call is what's recording now. Home shows it here (the call page owns
    // its controls); the Conversations tab has its own call banner instead.
    final call = context.watch<PhoneCallProvider>();
    final phoneCallState = call.callState;
    if (phoneCallState == PhoneCallState.active ||
        phoneCallState == PhoneCallState.connecting ||
        phoneCallState == PhoneCallState.ringing) {
      if (!widget.showsCall) return const SizedBox.shrink();
      final l10n = context.l10n;
      return Semantics(
        button: true,
        hint: l10n.openCall,
        child: GestureDetector(
          onTap: () => routeToPage(context, const ActiveCallPage()),
          child: _cardShell(
            LiveCaptureCard(
              source: LiveCaptureCard.callSource,
              stateLabel: switch (phoneCallState) {
                PhoneCallState.connecting => l10n.callStateConnecting,
                PhoneCallState.ringing => l10n.callStateRinging,
                _ => captureStateLabel(l10n, CaptureDisplayState.listening),
              },
              // Amber until audio flows: connecting and ringing are not listening yet.
              paused: phoneCallState != PhoneCallState.active,
              elapsed: phoneCallState == PhoneCallState.active ? call.callDuration : null,
              lastLine: call.transcriptSegments.lastOrNull?.text,
            ),
          ),
        ),
      );
    }

    return Consumer<CaptureProvider>(
      builder: (context, provider, child) {
        // The card means "what's recording now": hidden when nothing is (a connected pendant
        // that is not capturing, or a stopped phone). Transcribe Later keeps its own card.
        final batch = provider.isPhoneMicBatchRecording ||
            (SharedPreferencesUtil().batchModeEnabled && provider.havingRecordingDevice);
        final phoneLive = provider.recordingState == RecordingState.record ||
            provider.recordingState == RecordingState.initialising ||
            provider.recordingState == RecordingState.interrupted ||
            provider.recordingState == RecordingState.systemAudioRecord ||
            provider.isPhoneMicPaused;
        if (provider.liveCaptureSource == null && !phoneLive && !batch) {
          return const SizedBox.shrink();
        }

        return GestureDetector(
          onTap: () async {
            // Offline/batch mode has no live transcript — the card is informational,
            // so swallow taps instead of opening the (empty) capturing page. Covers both
            // device batch and the phone-mic Transcribe Later session.
            if (provider.isPhoneMicBatchRecording ||
                (SharedPreferencesUtil().batchModeEnabled && provider.havingRecordingDevice)) {
              return;
            }
            final isCaptureActive = provider.recordingState == RecordingState.record ||
                provider.recordingState == RecordingState.systemAudioRecord ||
                provider.recordingState == RecordingState.deviceRecord ||
                provider.recordingState == RecordingState.initialising ||
                provider.recordingState == RecordingState.interrupted ||
                provider.recordingState == RecordingState.pause ||
                provider.havingRecordingDevice ||
                provider.isPaused;
            if (!isCaptureActive && provider.segments.isEmpty && provider.photos.isEmpty) return;
            PlatformManager.instance.analytics.liveTranscriptCardClicked(
              hasSegments: provider.segments.isNotEmpty,
              hasPhotos: provider.photos.isNotEmpty,
              segmentCount: provider.segments.length,
              photoCount: provider.photos.length,
            );
            routeToPage(context, ConversationCapturingPage(topConversationId: provider.topConversationId));
          },
          child: Semantics(
            button: !batch,
            hint: batch ? null : context.l10n.liveTranscript,
            child: _cardShell(_buildUnifiedRecordingUI(provider)),
          ),
        );
      },
    );
  }

  Widget _cardShell(Widget child) => Container(
        margin: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        width: double.maxFinite,
        padding: const EdgeInsets.fromLTRB(18, 14, 12, 16),
        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(24)),
        child: child,
      );

  Future<void> _togglePause(CaptureProvider provider) async {
    final phone = provider.liveCaptureSource == 'phone';
    if (provider.isPaused) {
      OmiHaptics.medium();
      await provider.resumeCapture();
      if (phone) PlatformManager.instance.analytics.phoneMicRecordingStarted();
    } else {
      OmiHaptics.medium();
      await provider.pauseCapture();
      if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
    }
    PlatformManager.instance.analytics.recordingMuteToggled(
      isMuted: provider.isPaused,
      recordingType: phone ? 'phone_mic' : 'device',
    );
  }

  Widget _buildUnifiedRecordingUI(CaptureProvider provider) {
    // The controller names the source that owns the capture: a connected pendant the phone took
    // over from is not "device recording".
    final liveSource = provider.liveCaptureSource;
    bool isDeviceRecording = liveSource != null && liveSource != 'phone';

    // Offline/batch mode: device or phone-mic audio is saved locally with no live
    // transcription, so show a dedicated, self-explanatory card instead of the
    // "Listening" + transcript UI.
    if ((isDeviceRecording && SharedPreferencesUtil().batchModeEnabled) || provider.isPhoneMicBatchRecording) {
      return _buildBatchRecordingUI(provider);
    }

    // A phone-mic batch session reports RecordingState.record too; exclude it here so
    // the Live "Listening" card never renders for it (it is handled above).
    bool isPhoneRecording = !provider.isPhoneMicBatchRecording &&
        (provider.recordingState == RecordingState.record ||
            provider.recordingState == RecordingState.systemAudioRecord ||
            provider.recordingState == RecordingState.initialising ||
            provider.recordingState == RecordingState.interrupted ||
            provider.isPhoneMicPaused);

    // Determine pause state based on recording type.
    // Any audio-session interruption (call, other-app audio, system alert) is
    // treated as paused so the UI does not claim "Listening" while mute (#4706).
    bool isAudioInterrupted = provider.recordingState == RecordingState.interrupted;
    bool isPaused = false;
    if (isDeviceRecording) {
      isPaused = provider.isPaused && provider.recordingState == RecordingState.pause;
    } else if (isPhoneRecording) {
      isPaused = provider.isPhoneMicPaused || provider.isPaused || isAudioInterrupted;
    }
    final hasTerminalTranscriptionFailure = provider.terminalTranscriptionFailure != null;
    final bufferingFor = provider.customSttBufferingDuration;

    // Determine if this is an OmiGlass-type device (captures photos)
    bool hasPhotos = provider.photos.isNotEmpty;
    // Show "Listening" for all active recording states — WAL ensures audio is
    // saved locally regardless of transcription connection status.
    // Custom STT endpoint unreachable means audio is still buffering locally
    // (see customSttBufferingDuration / PurePollingSocket).
    String statusText = captureStateLabel(
      context.l10n,
      liveCaptureDisplayState(
        audioInterrupted: isAudioInterrupted,
        paused: isPaused,
        // One word for a pause, whatever the source: the control is Pause/Resume.
        transcriptionUnavailable: hasTerminalTranscriptionFailure,
        bufferingFor: bufferingFor,
        capturingPhotos: hasPhotos,
      ),
      bufferingFor: bufferingFor,
      compact: true,
    );

    // When recording is active: the one capture status and control surface.
    if (isDeviceRecording || isPhoneRecording) {
      final startedAt = provider.liveCaptureStartedAt;
      final card = LiveCaptureCard(
        source: isDeviceRecording ? liveSource : 'phone',
        stateLabel: statusText,
        paused: isPaused || hasTerminalTranscriptionFailure || bufferingFor != null,
        elapsed: startedAt == null ? null : DateTime.now().difference(startedAt),
        lastLine: provider.segments.lastOrNull?.text,
        note:
            isPhoneRecording && provider.pendantPausedForPhone ? context.l10n.pendantPausedResumesWhenYouFinish : null,
        // Photo-capture devices (OmiGlass) keep capturing photos; there is nothing to pause.
        onPauseToggle: !LiveCaptureCard.canPause(provider.recordingDevice, source: liveSource) || isAudioInterrupted
            ? null
            : () => _togglePause(provider),
      );
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          card,
          if (provider.isConversationMarkedForStarring) ...[
            const SizedBox(height: OmiSpacing.sm),
            Row(children: [
              const FaIcon(FontAwesomeIcons.solidStar, size: 12, color: OmiColors.textSecondary),
              const SizedBox(width: OmiSpacing.xs),
              Text(context.l10n.starred, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ]),
          ],
          if (hasPhotos) ...[
            const SizedBox(height: 12),
            PhotosPreviewWidget(photos: provider.photos),
          ],
        ],
      );
    } else if (provider.havingRecordingDevice && SharedPreferencesUtil().batchModeEnabled) {
      // Device connected in offline mode but not yet in the recording state above.
      return _buildBatchRecordingUI(provider);
    }
    return const SizedBox.shrink();
  }

  /// Offline/batch-mode capture card. Self-explanatory and informational only —
  /// there is no live transcript and no pause control (the native writer keeps
  /// saving regardless of the Dart stream). Shows a live "captured so far" timer
  /// for the current session. Tapping opens [_showOfflineModeInfoSheet].
  Widget _buildBatchRecordingUI(CaptureProvider provider) {
    final isPendant = provider.recordingDevice?.type == DeviceType.limitless;
    final prefs = SharedPreferencesUtil();
    final muted = !isPendant && provider.offlineMuted;
    // Native low-storage flag: capture is paused, so the card must not look healthy.
    // Read directly in build — CaptureController reloads prefs + notifies when it flips.
    final storageFull = !isPendant && prefs.getBool('batchStorageFull');
    final paused = muted || storageFull;
    final elapsed = provider.offlineRecordingElapsedSeconds;
    String? elapsedLabel;
    if (isPendant) {
      final minutesStored = (prefs.pendantPagesStored * 1.4 / 60).round();
      if (minutesStored > 0) elapsedLabel = context.l10n.pendantMinutesStored(minutesStored);
    } else if (elapsed != null) {
      elapsedLabel = '${elapsed ~/ 60}m ${(elapsed % 60).toString().padLeft(2, '0')}s';
    }
    final dotColor = paused ? Colors.grey.shade600 : OmiColors.danger;
    return Padding(
      padding: const EdgeInsets.only(left: 8, right: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: const Color(0xFF35343B), borderRadius: BorderRadius.circular(20)),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      storageFull
                          ? context.l10n.paused
                          : muted
                              ? context.l10n.paused
                              : context.l10n.recording,
                      style: const TextStyle(color: OmiColors.textSecondary, fontSize: 14, fontWeight: FontWeight.w500),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              if (elapsedLabel != null)
                Text(
                  elapsedLabel,
                  style: const TextStyle(
                    color: OmiColors.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    fontFeatures: [FontFeature.tabularFigures()],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            isPendant
                ? (prefs.pendantDraining ? context.l10n.pendantSyncingRecordings : context.l10n.pendantRecordingNote)
                : storageFull
                    ? context.l10n.transcribeLaterStorageFull
                    : (muted ? context.l10n.transcribeLaterPaused : context.l10n.transcribeLaterNote),
            style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.35),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          if (isPendant && prefs.pendantStorageAlmostFull) ...[
            const SizedBox(height: 8),
            Text(
              context.l10n.pendantStorageAlmostFull,
              style: TextStyle(color: Colors.orange.shade300, fontSize: 12, height: 1.3),
            ),
          ],
          // Mute / New recording drive the native writer prefs, which the pendant
          // drain path doesn't use — the pendant records on its own.
          if (!isPendant) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                _buildOfflineControl(
                  // Pause glyphs, as on the live card: mics belong to Ask Omi.
                  icon: muted ? FontAwesomeIcons.play : FontAwesomeIcons.pause,
                  label: muted ? context.l10n.resume : context.l10n.pause,
                  primary: false,
                  onTap: () async {
                    try {
                      await provider.toggleOfflineMute();
                    } catch (_) {
                      if (mounted) AppSnackbar.showSnackbar(context.l10n.somethingWentWrong);
                    }
                  },
                ),
                const SizedBox(width: 10),
                _buildOfflineControl(
                  icon: FontAwesomeIcons.circlePlus,
                  label: context.l10n.newRecording,
                  primary: true,
                  onTap: () => provider.startNewOfflineRecording(),
                ),
              ],
            ),
            // Phone-mic batch is user-driven (not ambient like BLE), so it needs an
            // explicit Stop that ends the session. BLE batch has no Stop by design.
            if (provider.isPhoneMicBatchRecording) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  _buildOfflineControl(
                    icon: FontAwesomeIcons.stop,
                    label: context.l10n.stop,
                    primary: false,
                    onTap: () => provider.stopStreamRecording(),
                  ),
                ],
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _buildOfflineControl({
    required FaIconData icon,
    required String label,
    required bool primary,
    required VoidCallback onTap,
  }) {
    final color = primary ? Colors.white : OmiColors.textSecondary;
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: primary ? const Color(0xFF35343B) : const Color(0xFF2A2A2E),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              FaIcon(icon, size: 16, color: color),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RecordingStatusIndicator extends StatefulWidget {
  const RecordingStatusIndicator({super.key});

  @override
  State<RecordingStatusIndicator> createState() => _RecordingStatusIndicatorState();
}

class _RecordingStatusIndicatorState extends State<RecordingStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: const Icon(Icons.fiber_manual_record, color: Colors.red, size: 16.0),
    );
  }
}

class PausedStatusIndicator extends StatefulWidget {
  const PausedStatusIndicator({super.key});

  @override
  State<PausedStatusIndicator> createState() => _PausedStatusIndicatorState();
}

class _PausedStatusIndicatorState extends State<PausedStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: const Icon(Icons.fiber_manual_record, color: Colors.orange, size: 16.0),
    );
  }
}

getPhoneMicRecordingButton(
  BuildContext context,
  VoidCallback toggleRecordingCb,
  RecordingState currentActualState, {
  bool isPhoneMicPaused = false,
}) {
  if (SharedPreferencesUtil().btDevice.id.isNotEmpty) {
    // If a BT device is configured and we are NOT on desktop, don't show this button.
    return const SizedBox.shrink();
  }
  String text;
  Widget icon;
  bool isLoading = currentActualState == RecordingState.initialising;

  // Phone Mic
  {
    if (isLoading) {
      text = context.l10n.initialisingRecorder;
      icon = const OmiSpinner(size: OmiSpinnerSize.small);
    } else if (currentActualState == RecordingState.record) {
      text = context.l10n.pauseRecording;
      icon = Container(
        margin: const EdgeInsets.only(right: 4),
        width: 24,
        height: 24,
        decoration: const BoxDecoration(color: Colors.orange, shape: BoxShape.circle),
        child: const Center(child: Icon(Icons.pause, color: Colors.white, size: 14)),
      );
    } else if (isPhoneMicPaused) {
      text = context.l10n.resumeRecording;
      icon = Container(
        margin: const EdgeInsets.only(right: 4),
        width: 24,
        height: 24,
        decoration: const BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
        child: const Center(child: Icon(Icons.play_arrow, color: OmiColors.onAccent, size: 14)),
      );
    } else {
      text = context.l10n.continueRecording;
      icon = const Icon(Icons.mic, size: 18);
    }
  }

  return MaterialButton(
    onPressed: isLoading ? null : toggleRecordingCb,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        icon,
        const SizedBox(width: 4),
        Text(
          text,
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white, fontWeight: FontWeight.w500),
        ),
        const SizedBox(width: 4),
      ],
    ),
  );
}

Widget getProcessingConversationsWidget(List<ServerConversation> conversations) {
  // Only show at most 1 processing widget on homepage
  if (conversations.isEmpty) {
    return const SliverToBoxAdapter(child: SizedBox.shrink());
  }
  // Live events append new IDs; list position is not recency. Processing begins
  // at capture end, while the optimistic Process Now row has only createdAt.
  final newest = conversations.reduce((a, b) {
    final aTime = a.finishedAt ?? a.createdAt;
    final bTime = b.finishedAt ?? b.createdAt;
    return bTime.isAfter(aTime) ? b : a;
  });
  return SliverToBoxAdapter(
    child: ProcessingConversationWidget(key: ValueKey('processing_${newest.id}'), conversation: newest),
  );
}

// PROCESSING CONVERSATION

class ProcessingConversationWidget extends StatefulWidget {
  final ServerConversation conversation;

  /// Optional clock override for tests.
  final DateTime Function()? now;

  /// Optional reprocess override for tests.
  final Future<ServerConversation?> Function(String conversationId)? reprocess;

  const ProcessingConversationWidget({super.key, required this.conversation, this.now, this.reprocess});

  @override
  State<ProcessingConversationWidget> createState() => _ProcessingConversationWidgetState();
}

class _ProcessingConversationWidgetState extends State<ProcessingConversationWidget> {
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
  void didUpdateWidget(ProcessingConversationWidget oldWidget) {
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
        provider.addProcessingConversation(updated);
      } else {
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
                        color: const Color(0xFF35343B),
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
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 13, height: 1.3),
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
                          foregroundColor: Colors.white,
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
