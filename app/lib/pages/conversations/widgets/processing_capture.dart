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
import 'package:omi/providers/device_provider.dart';
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
  const ConversationCaptureWidget({super.key, this.showsCall = false, this.idle});

  /// Home shows an Omi call on this card; the Conversations tab has its own call banner.
  final bool showsCall;

  /// Shown when nothing records (Home's "Not listening" card). A pendant that dropped mid-capture
  /// shows its Disconnected card in this place instead, so the two never stack.
  final Widget? idle;

  @override
  State<ConversationCaptureWidget> createState() => _ConversationCaptureWidgetState();
}

class _ConversationCaptureWidgetState extends State<ConversationCaptureWidget> {
  Timer? _offlineTicker;
  int _offlineTick = 0;

  /// The pendant capture this card last showed, kept so a pendant that drops mid-capture shows as
  /// Disconnected instead of the card vanishing. The controller forgets the device on disconnect
  /// (`liveCaptureSource` goes null, just as when nothing ever recorded), so "was capturing" is
  /// remembered here: set while a realtime pendant capture is live, cleared when the pendant
  /// reconnects, is unpaired, or another source (the phone) takes over.
  String? _droppedSource;
  DateTime? _droppedStartedAt;

  /// When the drop was first seen: the card's time stops there, since nothing records meanwhile.
  DateTime? _droppedAt;

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
            padding: _liveCardPadding,
            LiveCaptureCard(
              source: LiveCaptureCard.callSource,
              // Connecting and ringing say so, with no time: they are not listening yet.
              status: switch (phoneCallState) {
                PhoneCallState.connecting => l10n.callStateConnecting,
                PhoneCallState.ringing => l10n.callStateRinging,
                _ => captureStateLabel(l10n, CaptureDisplayState.listening),
              },
              // Amber until audio flows: connecting and ringing are not listening yet.
              live: phoneCallState == PhoneCallState.active,
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
        final (pendantConnected, pendantPaired, pendantConnecting) = context.select<DeviceProvider, (bool, bool, bool)>(
          (d) => (d.connectedDevice != null, d.pairedDevice?.id.isNotEmpty ?? false, d.isConnecting),
        );
        final pendantDropped = _trackPendantDrop(provider, connected: pendantConnected, paired: pendantPaired);
        if (pendantDropped) {
          return _cardShell(_buildPendantDroppedUI(provider, reconnecting: pendantConnecting),
              padding: _liveCardPadding);
        }
        final phoneLive = provider.recordingState == RecordingState.record ||
            provider.recordingState == RecordingState.initialising ||
            provider.recordingState == RecordingState.interrupted ||
            provider.recordingState == RecordingState.systemAudioRecord ||
            provider.isPhoneMicPaused;
        // Nothing recording, or the reader pressed Stop (a stopped pendant waits for Start; a Stop
        // still on its way already reads as stopped).
        if ((provider.liveCaptureSource == null && !phoneLive && !batch) ||
            (provider.isCaptureStopped && !phoneLive) ||
            provider.isStopping) {
          return widget.idle ?? const SizedBox.shrink();
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
            child: _cardShell(_buildUnifiedRecordingUI(provider), padding: _liveCardPadding),
          ),
        );
      },
    );
  }

  /// The live card's orb, wave and capsules sit on the design's 16pt card padding.
  static const _liveCardPadding = EdgeInsets.all(OmiSpacing.md);

  /// The live card (Liquid Dock): a 28 pt card with the design's rim and top light.
  Widget _cardShell(Widget child, {EdgeInsets? padding}) => Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.sm),
        child: OmiCard(
          radius: OmiRadius.cardLarge,
          padding: padding ?? const EdgeInsets.all(OmiSpacing.md),
          child: SizedBox(width: double.maxFinite, child: child),
        ),
      );

  /// Updates the remembered pendant capture and says whether it dropped: no source is live, the
  /// pendant it came from is still paired but not connected. See [_droppedSource].
  bool _trackPendantDrop(CaptureProvider provider, {required bool connected, required bool paired}) {
    final source = provider.liveCaptureSource;
    if (provider.isCaptureStopped) {
      // Stopped is not capturing: a pendant that drops now has nothing to lose.
      _droppedSource = null;
      _droppedStartedAt = null;
      _droppedAt = null;
      return false;
    }
    if (source != null && source != 'phone' && !SharedPreferencesUtil().batchModeEnabled) {
      _droppedSource = source;
      _droppedStartedAt = provider.liveCaptureStartedAt ?? _droppedStartedAt;
      _droppedAt = null;
      return false;
    }
    if (source != null || connected || !paired) {
      _droppedSource = null;
      _droppedStartedAt = null;
      _droppedAt = null;
      return false;
    }
    if (_droppedSource == null) return false;
    _droppedAt ??= DateTime.now();
    return true;
  }

  Widget _buildPendantDroppedUI(CaptureProvider provider, {required bool reconnecting}) {
    final l10n = context.l10n;
    final startedAt = _droppedStartedAt;
    return LiveCaptureCard(
      source: _droppedSource!,
      status: l10n.disconnected,
      detail: reconnecting ? l10n.reconnecting : null,
      explanation: l10n.capturePendantDisconnectedDetail,
      live: false,
      elapsed: startedAt == null ? null : (_droppedAt ?? DateTime.now()).difference(startedAt),
      lastLine: provider.segments.lastOrNull?.text,
    );
  }

  /// Stop: saves this conversation and stops listening until Start ([CaptureController.stopCapture]),
  /// as the Live page's Stop and the Lock Screen's do.
  Future<void> _finish(CaptureProvider provider) async {
    final phone = provider.liveCaptureSource == 'phone' || provider.liveCaptureSource == null;
    // "Finish a conversation": a success notification (the Haptics board).
    OmiHaptics.success();
    try {
      await provider.stopCapture();
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
      return;
    }
    if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
  }

  /// Mute or Unmute, whichever the card shows ([muted]), so the tap always does what it says.
  Future<void> _togglePause(CaptureProvider provider, {required bool muted}) async {
    final phone = provider.liveCaptureSource == 'phone';
    try {
      OmiHaptics.medium();
      if (muted) {
        await provider.resumeCapture();
        // Still muted: say so rather than leave a button that seems to do nothing.
        if (provider.isPaused) throw StateError('capture stayed muted');
        if (phone) PlatformManager.instance.analytics.phoneMicRecordingStarted();
      } else {
        await provider.pauseCapture();
        if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
      }
    } catch (_) {
      // Same as the live page's control: say so rather than leave an unhandled future.
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
      return;
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

    // A pause the reader chose (the control reads Resume only then).
    final isAudioInterrupted = provider.recordingState == RecordingState.interrupted;
    bool isPaused = false;
    if (isDeviceRecording) {
      isPaused = provider.isPaused && provider.recordingState == RecordingState.pause;
    } else if (isPhoneRecording) {
      isPaused = provider.isPhoneMicPaused || provider.isPaused;
    }
    // `interrupted` is the OS holding the mic (explained, no control) or capture recovering on its
    // own (Reconnecting, Pause still works); a reader pause keeps Resume either way.
    final interruption = captureInterruption(
      interrupted: isPhoneRecording && isAudioInterrupted,
      readerPaused: isPaused,
      osHoldsMic: provider.isCallActive,
    );
    final micTaken = interruption == CaptureInterruption.micTaken;
    final hasTerminalTranscriptionFailure = provider.terminalTranscriptionFailure != null;
    final bufferingFor = provider.customSttBufferingDuration;

    // Determine if this is an OmiGlass-type device (captures photos)
    bool hasPhotos = provider.photos.isNotEmpty;
    // WAL saves audio locally whatever the transcription connection does, so a degraded
    // transcription names the consequence ("Audio saved, transcribes later"), not a stop.
    final displayState = liveCaptureDisplayState(
      audioInterrupted: micTaken,
      paused: isPaused,
      transcriptionUnavailable: hasTerminalTranscriptionFailure,
      bufferingFor: bufferingFor,
      reconnecting: interruption == CaptureInterruption.recovering,
      capturingPhotos: hasPhotos,
    );
    // Initialising: the microphone is opening and no audio flows yet, so it is not Listening.
    final starting = isPhoneRecording &&
        provider.recordingState == RecordingState.initialising &&
        displayState == CaptureDisplayState.listening;
    final copy = starting
        ? CaptureCardCopy(context.l10n.captureStarting)
        : captureCardCopy(context.l10n, displayState, micTaken: micTaken, socketDown: !provider.transcriptServiceReady);

    // When recording is active: the one capture status and control surface.
    if (isDeviceRecording || isPhoneRecording) {
      final startedAt = provider.liveCaptureStartedAt;
      final card = LiveCaptureCard(
        source: isDeviceRecording ? liveSource : 'phone',
        status: copy.status,
        detail: copy.detail,
        explanation: copy.explanation,
        // Unmute only when the status says Muted; a degraded transcription is still live, so its
        // control is Mute.
        paused: isPaused,
        // The LED means audio is being captured now: not while paused, the OS holds the mic, or the
        // microphone is still opening.
        live: !isPaused && !micTaken && !starting,
        // The one capture clock: it stands still while muted, and every surface shows the same time.
        elapsed: startedAt == null ? null : provider.captureElapsed,
        lastLine: provider.segments.lastOrNull?.text,
        note:
            isPhoneRecording && provider.pendantPausedForPhone ? context.l10n.pendantPausedResumesWhenYouFinish : null,
        // Photo-capture devices (OmiGlass) keep capturing photos; there is nothing to mute.
        onPauseToggle: !provider.canMuteLiveSource || micTaken ? null : () => _togglePause(provider, muted: isPaused),
        onFinish: () => _finish(provider),
      );
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          card,
          if (provider.isConversationMarkedForStarring) ...[
            const SizedBox(height: OmiSpacing.sm),
            Row(children: [
              FaIcon(FontAwesomeIcons.solidStar, size: 12, color: OmiColors.textSecondary),
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

  /// Transcribe Later (batch) card, in the live card's layout: the source glyph, a short status and
  /// the time with its consequence, then the controls. There is no live transcript. Storage running
  /// out is a problem (warning glyph, details sheet); a pendant that records on its own (Limitless)
  /// shows the minutes it holds and has no controls, since it records without the phone.
  Widget _buildBatchRecordingUI(CaptureProvider provider) {
    final l10n = context.l10n;
    final isLimitless = provider.recordingDevice?.type == DeviceType.limitless;
    final prefs = SharedPreferencesUtil();
    final muted = !isLimitless && provider.offlineMuted;
    // Native low-storage flag: capture is paused, so the card must not look healthy.
    // Read directly in build — CaptureController reloads prefs + notifies when it flips.
    final storageFull = !isLimitless && prefs.getBool('batchStorageFull');
    final source = provider.isPhoneMicBatchRecording
        ? 'phone'
        : (provider.liveCaptureSource ?? (isLimitless ? 'limitless' : 'omi'));
    final elapsedSeconds = provider.offlineRecordingElapsedSeconds;

    final CaptureCardCopy copy;
    String? note;
    if (isLimitless) {
      final minutesStored = (prefs.pendantPagesStored * 1.4 / 60).round();
      final almostFull = prefs.pendantStorageAlmostFull;
      final detail = [
        if (minutesStored > 0) l10n.pendantMinutesStored(minutesStored),
        if (almostFull) l10n.captureStorageAlmostFull,
      ].join('  ·  ');
      copy = CaptureCardCopy(l10n.recording,
          detail: detail.isEmpty ? null : detail, explanation: almostFull ? l10n.pendantStorageAlmostFull : null);
      note = prefs.pendantDraining ? l10n.pendantSyncingRecordings : l10n.pendantRecordingNote;
    } else if (storageFull) {
      copy = CaptureCardCopy(l10n.paused,
          detail: l10n.capturePhoneStorageFull, explanation: l10n.transcribeLaterStorageFull);
    } else if (muted) {
      copy = CaptureCardCopy(l10n.muted);
    } else {
      copy = CaptureCardCopy(l10n.recording, detail: l10n.captureAudioSavedTranscribesLater);
    }

    final actions = <_OfflineAction>[
      // Mute, as on the live card. Storage-full is already paused.
      if (!isLimitless && !storageFull)
        (
          icon: muted ? Icons.mic_rounded : Icons.mic_off_rounded,
          label: muted ? l10n.unmute : l10n.mute,
          onTap: () async {
            try {
              await provider.toggleOfflineMute();
            } catch (_) {
              if (mounted) AppSnackbar.showSnackbar(context.l10n.somethingWentWrong);
            }
          },
        ),
      // Mute / New recording drive the native writer prefs, which the Limitless drain path doesn't
      // use — that pendant records on its own. The phone's session has Stop instead (two controls at
      // most; Stop then Start is a new recording).
      if (!isLimitless && !provider.isPhoneMicBatchRecording)
        (icon: Icons.add_circle_outline_rounded, label: l10n.newRecording, onTap: provider.startNewOfflineRecording),
      // Phone-mic batch is user-driven (not ambient like BLE), so it needs an explicit Stop that ends
      // the session. BLE batch has no Stop by design.
      if (provider.isPhoneMicBatchRecording)
        (
          icon: Icons.stop_rounded,
          label: l10n.stop,
          onTap: () async {
            try {
              await provider.stopStreamRecording();
            } catch (_) {
              if (mounted) AppSnackbar.showSnackbar(context.l10n.somethingWentWrong);
            }
          },
        ),
    ];

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LiveCaptureCard(
          source: source,
          status: copy.status,
          detail: copy.detail,
          explanation: copy.explanation,
          // A Limitless pendant records on its own; the phone's writer stops when muted or full.
          live: isLimitless || (!muted && !storageFull),
          elapsed: isLimitless || elapsedSeconds == null ? null : Duration(seconds: elapsedSeconds),
          note: note,
        ),
        if (actions.isNotEmpty) ...[
          const SizedBox(height: OmiSpacing.sm),
          Padding(padding: const EdgeInsets.only(right: OmiSpacing.xxs), child: _OfflineControls(actions: actions)),
        ],
      ],
    );
  }
}

typedef _OfflineAction = ({IconData icon, String label, VoidCallback onTap});

/// The Transcribe Later controls: the first two side by side when both labels fit whole at the
/// current width and text size, otherwise one per row; Stop always takes its own row. Each is an
/// [OmiButton] (a 44pt+ target).
class _OfflineControls extends StatelessWidget {
  const _OfflineControls({required this.actions});

  final List<_OfflineAction> actions;

  static const _gap = OmiSpacing.xs;

  OmiButton _button(_OfflineAction a) =>
      OmiButton.secondary(label: a.label, icon: a.icon, onPressed: a.onTap, size: OmiButtonSize.compact, expand: true);

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final scaler = MediaQuery.textScalerOf(context);
      final direction = Directionality.of(context);
      // The ambient text style supplies the platform font the button label resolves to.
      final labelStyle =
          DefaultTextStyle.of(context).style.merge(OmiType.subhead.copyWith(fontWeight: FontWeight.w600));
      // What a compact OmiButton needs to show its label whole: padding, glyph, gap and text.
      double needed(String label) {
        final painter = TextPainter(
          text: TextSpan(text: label, style: labelStyle),
          textDirection: direction,
          textScaler: scaler,
          maxLines: 1,
        )..layout();
        final width = painter.width;
        painter.dispose();
        return width + 2 * OmiSpacing.md + 16 + OmiSpacing.xs + 2;
      }

      final paired = actions.length >= 2 &&
          actions.take(2).map((a) => needed(a.label)).reduce((a, b) => a > b ? a : b) * 2 + _gap <=
              constraints.maxWidth;
      final rows = <Widget>[
        if (paired)
          Row(children: [
            Expanded(child: _button(actions[0])),
            const SizedBox(width: _gap),
            Expanded(child: _button(actions[1])),
          ]),
        for (final a in actions.skip(paired ? 2 : 0)) _button(a),
      ];
      return Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (var i = 0; i < rows.length; i++) ...[if (i > 0) const SizedBox(height: _gap), rows[i]],
      ]);
    });
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
      // v2: the LED colour means "audio is being captured right now".
      child: Icon(Icons.fiber_manual_record, color: OmiColors.live, size: 16.0),
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
      child: Icon(Icons.fiber_manual_record, color: OmiColors.warning, size: 16.0),
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
        decoration: BoxDecoration(color: OmiColors.warning, shape: BoxShape.circle),
        child: const Center(child: Icon(Icons.pause, color: Colors.white, size: 14)),
      );
    } else if (isPhoneMicPaused) {
      text = context.l10n.resumeRecording;
      icon = Container(
        margin: const EdgeInsets.only(right: 4),
        width: 24,
        height: 24,
        decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
        child: Center(child: Icon(Icons.play_arrow, color: OmiColors.onAccent, size: 14)),
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
          style: Theme.of(context)
              .textTheme
              .bodyMedium!
              .copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w500),
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
                        color: OmiColors.surface4,
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
                    style: TextStyle(color: OmiColors.textSecondary, fontSize: 13, height: 1.3),
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
