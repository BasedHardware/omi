import 'package:omi/pages/phone_calls/phone_calls_feature.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/conversations/live_capture_summary.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/home/widgets/home_capture_sheet.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/home/widgets/home_bottom_controls.dart';
import 'package:omi/pages/home/widgets/grow_route.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/header_circle_button.dart';

/// The header pills paint 36pt tall; this transparent margin, inside an opaque
/// GestureDetector, makes the touch target [kMinTapTarget] without moving them
/// (the app bar centers the row, and the toolbar is taller than the target).
const EdgeInsets _pillTargetMargin = EdgeInsets.symmetric(vertical: (kMinTapTarget - 36) / 2);

/// Battery at or below this shows a low-battery glyph and a warning colour, not just a dot.
const int kLowBatteryPercent = 20;

class BatteryInfoWidget extends StatefulWidget {
  const BatteryInfoWidget({super.key});

  @override
  State<BatteryInfoWidget> createState() => _BatteryInfoWidgetState();
}

class _BatteryInfoWidgetState extends State<BatteryInfoWidget> {
  @override
  Widget build(BuildContext context) {
    return Selector<HomeProvider, bool>(
      selector: (context, state) => state.selectedIndex == 0,
      builder: (context, isMemoriesPage, child) {
        // Use Selector to only rebuild when battery level, connected device, or connecting state changes
        // This reduces battery drain by avoiding unnecessary rebuilds during other provider updates
        return Selector<DeviceProvider, (int, BtDevice?, BtDevice?, bool, bool)>(
          selector: (_, provider) => (
            provider.batteryLevel,
            provider.connectedDevice,
            provider.pairedDevice,
            provider.isConnecting,
            provider.isCharging,
          ),
          builder: (context, data, child) {
            final (batteryLevel, connectedDevice, pairedDevice, isConnecting, isCharging) = data;
            final l10n = context.l10n;
            if (connectedDevice != null) {
              final hasBattery = batteryLevel > 0;
              final low = hasBattery && batteryLevel <= kLowBatteryPercent && !isCharging;
              final semantics = [
                connectedDevice.name,
                if (hasBattery) l10n.batteryLevelSemantics(batteryLevel),
                if (isCharging) l10n.charging,
              ].join(', ');
              final batteryPill = _DevicePill(
                semanticsLabel: semantics,
                onTap: () {
                  OmiHaptics.selection();
                  routeToPage(context, const ConnectedDevice());
                  PlatformManager.instance.analytics.batteryIndicatorClicked();
                },
                children: [
                  _SyncRing(
                    child: SizedBox(
                      width: 16,
                      height: 16,
                      child: Image.asset(
                        DeviceUtils.getDeviceImagePath(
                          deviceType: connectedDevice.type,
                          modelNumber: connectedDevice.modelNumber,
                          deviceName: connectedDevice.name,
                        ),
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                  // Only show battery indicator and percentage when battery level is valid (> 0)
                  if (hasBattery) ...[
                    const SizedBox(width: 6.0),
                    // Battery only: a bar glyph, never a coloured dot (live status lives on the
                    // capture card). Red appears only when critically low.
                    if (isCharging) ...[
                      Icon(Icons.bolt, color: OmiColors.textSecondary, size: 13),
                      const SizedBox(width: 1),
                    ],
                    BatteryGlyph(level: batteryLevel, critical: low),
                    const SizedBox(width: 4.0),
                    Text(
                      '$batteryLevel%',
                      style: OmiType.caption.copyWith(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: low ? OmiColors.danger : OmiColors.textPrimary,
                      ),
                    ),
                  ],
                ],
              );
              if (!isMemoriesPage || !PhoneCallsFeature.visible) return batteryPill;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  batteryPill,
                  // 8pt between the painted shapes; the button's 44pt target overhangs
                  // its 36pt circle by 4pt.
                  const SizedBox(width: 4),
                  HeaderCircleButton(
                    semanticLabel: l10n.phoneCallsWithOmi,
                    icon: Icon(
                      Icons.phone_in_talk_rounded,
                      color: OmiColors.active == OmiPalette.light ? OmiColors.textPrimary : Colors.white,
                      size: 16,
                    ),
                    onTap: () {
                      OmiHaptics.selection();
                      routeToPage(context, const PhoneCallsPage());
                    },
                  ),
                ],
              );
            } else if (pairedDevice != null && pairedDevice.id.isNotEmpty) {
              // Paired but not connected: "Connecting…" while a reconnect runs, otherwise one word,
              // "Disconnected" (the device page uses the same word).
              final status = isConnecting ? l10n.deviceConnecting : l10n.disconnected;
              return _DevicePill(
                semanticsLabel: '${pairedDevice.name}, $status',
                onTap: () async {
                  OmiHaptics.selection();
                  await routeToPage(context, const ConnectedDevice());
                },
                children: [
                  // Device icon with slash line
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: Stack(
                      children: [
                        Image.asset(DeviceUtils.getDeviceImageFromBtDevice(pairedDevice), fit: BoxFit.contain),
                        if (!isConnecting) Positioned.fill(child: CustomPaint(painter: SlashLinePainter())),
                      ],
                    ),
                  ),
                  const SizedBox(width: 6.0),
                  Flexible(
                    child: Text(status,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.caption.copyWith(fontSize: 12, color: OmiColors.textSecondary)),
                  ),
                ],
              );
            } else {
              final label = isConnecting ? l10n.searching : l10n.connect;
              return _DevicePill(
                semanticsLabel: label,
                onTap: () async {
                  OmiHaptics.selection();
                  if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                    routeToPage(context, const ConnectDevicePage());
                    PlatformManager.instance.analytics.connectFriendClicked();
                  } else {
                    await routeToPage(context, const ConnectedDevice());
                  }
                },
                children: [
                  // The asset is white; tint it so it shows on the light pill too.
                  Image.asset(Assets.images.logoTransparent.path, width: 16, height: 16, color: OmiColors.textPrimary),
                  // The word stays on every page (the logo alone reads as a loading spinner); it gives
                  // way with an ellipsis so the header fits narrow screens and large text.
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(label,
                        maxLines: 1, overflow: TextOverflow.ellipsis, style: OmiType.caption.copyWith(fontSize: 12)),
                  ),
                ],
              );
            }
          },
        );
      },
    );
  }
}

/// The quiet sync indicator: a thin ring circles the device glyph while offline sync or
/// processing runs. No words on the pill; the device page says what is happening.
class _SyncRing extends StatelessWidget {
  const _SyncRing({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final syncing = context.select<SyncProvider?, bool>((s) => s?.isSyncing ?? false);
    final processing =
        context.select<ConversationProvider?, bool>((c) => c?.processingConversations.isNotEmpty ?? false);
    return ListenableBuilder(
      listenable: PendingWorkStore.instance,
      builder: (context, _) => OmiActivityRing(
        key: const Key('device_pill_sync_ring'),
        active: syncing || processing || PendingWorkStore.instance.pending.isNotEmpty,
        diameter: 22,
        child: child,
      ),
    );
  }
}

/// A 36pt header pill inside a 44pt target, announced as one button (device details / connect).
class _DevicePill extends StatelessWidget {
  const _DevicePill({required this.semanticsLabel, required this.onTap, required this.children});

  final String semanticsLabel;
  final VoidCallback onTap;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticsLabel,
      // excludeSemantics drops the GestureDetector's own tap action, so the node carries it.
      onTap: onTap,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: 36,
          margin: _pillTargetMargin,
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
          child: Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.center, children: children),
        ),
      ),
    );
  }
}

/// Home's main bottom control, a light pill beside Ask Omi:
/// - "+ New" starts a recording with the phone, and the live transcript grows out of the pill;
/// - "Stop" while the phone records (its status is the card at the top of Home);
/// - with a device connected, the device itself: its picture, what it is doing and its battery.
///   Tap opens what it is capturing; hold offers the phone instead.
/// Long-press on "New" opens the record options sheet (phone call) when calls are offered, and a
/// one-time tip points that out after the first recording.
class HomeRecordButton extends StatefulWidget {
  const HomeRecordButton({super.key});

  @override
  State<HomeRecordButton> createState() => _HomeRecordButtonState();
}

class _HomeRecordButtonState extends State<HomeRecordButton> {
  static const _optionsTipKey = 'v2/homeRecordOptionsTipShown';

  /// Finishing takes a moment (the last audio is flushed): the pill says so at once.
  bool _stopping = false;

  /// The phone recording is this pill's own: live, paused, or reconnecting to transcription.
  static bool _phoneOwnsCapture(CaptureProvider capture) {
    final state = capture.recordingState;
    return state == RecordingState.record ||
        capture.isPhoneMicPaused ||
        (state == RecordingState.interrupted && capture.liveCaptureSource == 'phone');
  }

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
    if (_phoneOwnsCapture(captureProvider)) {
      // The phone recording is this button's own: finish it (processed, except Transcribe Later,
      // whose local file is finalized on stop), then any pendant it paused resumes.
      if (_stopping) return;
      setState(() => _stopping = true);
      try {
        await captureProvider.finishCapture();
      } finally {
        if (mounted) setState(() => _stopping = false);
      }
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
    if (context.mounted) _openTranscript(context);
  }

  /// The pendant capture the pill last showed, so a pendant that drops mid-capture reads as
  /// Disconnected instead of the pill going back to New. The controller forgets the device on
  /// disconnect, so "was capturing" is remembered here and cleared when it reconnects, is unpaired,
  /// or another source takes over.
  String? _droppedSource;

  bool _trackPendantDrop(CaptureProvider capture, {required bool connected, required bool paired}) {
    final source = capture.liveCaptureSource;
    if (source != null && source != 'phone' && !SharedPreferencesUtil().batchModeEnabled) {
      _droppedSource = source;
      return false;
    }
    if (source != null || connected || !paired) {
      _droppedSource = null;
      return false;
    }
    return _droppedSource != null;
  }

  /// The status the pill shows: the state and its short detail ("Recording · Audio saved…").
  static String _pillStatus(LiveCaptureSummary summary) {
    final detail = summary.copy.detail;
    if (detail == null || detail.isEmpty) return summary.copy.status;
    return '${summary.copy.status} · $detail';
  }

  Future<void> _resume(BuildContext context) async {
    OmiHaptics.medium();
    try {
      await context.read<CaptureProvider>().resumeCapture();
      PlatformManager.instance.analytics.phoneMicRecordingStarted();
    } catch (_) {
      if (context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
  }

  /// Everything the old Home card said and offered, on demand: why (when something needs a look),
  /// the capture's own controls (Pause/Resume, Transcribe Later's New recording and Stop, retrying
  /// transcription), and the way to the live transcript.
  void _showCaptureSheet(BuildContext context, LiveCaptureSummary? summary) {
    final l10n = context.l10n;
    final capture = context.read<CaptureProvider>();
    final phoneLive = _phoneOwnsCapture(capture) && !capture.isPhoneMicBatchRecording;
    showOmiSheet<void>(
      context: context,
      title: summary?.copy.status ?? l10n.listening,
      builder: (sheetContext) => HomeCaptureSheet(
        explanation: summary?.copy.explanation,
        onOpenTranscript: summary != null && !summary.batch
            ? () {
                Navigator.pop(sheetContext);
                if (context.mounted) _openTranscript(context);
              }
            : null,
        onStop: phoneLive
            ? () {
                Navigator.pop(sheetContext);
                // Only ever finishes: the recording may have ended while the sheet was open, and
                // the record toggle would then start a new one.
                if (context.mounted && _phoneOwnsCapture(context.read<CaptureProvider>())) {
                  _startPhoneRecording(context);
                }
              }
            : null,
      ),
    );
  }

  void _showDroppedSheet(BuildContext context) {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.disconnected,
      builder: (sheetContext) => HomeCaptureSheet(
        explanation: context.l10n.capturePendantDisconnectedDetail,
        showCard: false,
        // The pendant may be gone for a while: recording with the phone stays one tap away.
        onRecordWithPhone: () {
          Navigator.pop(sheetContext);
          if (context.mounted) _startPhoneRecording(context);
        },
      ),
    );
  }

  final GlobalKey _pillKey = GlobalKey();

  /// The live transcript, grown out of this pill.
  void _openTranscript(BuildContext context) {
    final capture = context.read<CaptureProvider>();
    pushGrowingFrom<void>(
      context,
      from: _pillKey,
      page: LiveEpisodePage(topConversationId: capture.topConversationId, initialTab: LiveEpisodeTab.transcript),
    );
  }

  /// The capturing pendant's pill: its live transcript, or the call while an Omi call owns it.
  void _openDevice(BuildContext context) {
    OmiHaptics.selection();
    if (_callInProgress(context)) {
      routeToPage(context, const ActiveCallPage());
      return;
    }
    final capture = context.read<CaptureProvider>();
    PlatformManager.instance.analytics.liveTranscriptCardClicked(
      hasSegments: capture.segments.isNotEmpty,
      hasPhotos: capture.photos.isNotEmpty,
      segmentCount: capture.segments.length,
      photoCount: capture.photos.length,
    );
    _openTranscript(context);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final capture = context.watch<CaptureProvider>();
    final device = context.select<DeviceProvider, BtDevice?>((d) => d.connectedDevice);
    final starting = capture.recordingState == RecordingState.initialising;
    // The pendant stands in for "New" only while it is capturing live; connected but idle (or
    // saving for Transcribe Later), the phone is still one tap away and the header shows the device.
    final pendantCapturing = device != null && _pendantHasCapture(capture);
    // A phone recording that is starting already looks live, so the pill changes the moment it is
    // tapped instead of after the microphone is up (Home shows no separate card meanwhile).
    final phoneRecording = _phoneOwnsCapture(capture) || (starting && !pendantCapturing);
    // The options sheet only adds a phone call; with calls hidden there is nothing else to offer.
    final canShowOptions = PhoneCallsFeature.visible && !phoneRecording && !starting;

    // What is recording and how it is going: the same summary the details sheet shows.
    final summary = summarizeLiveCapture(l10n, capture);
    final paired = context.select<DeviceProvider, BtDevice?>((d) => d.pairedDevice);
    final pendantConnecting = context.select<DeviceProvider, bool>((d) => d.isConnecting);
    final dropped = _trackPendantDrop(capture, connected: device != null, paired: paired != null);
    final pendantBatch = summary != null && summary.batch && !summary.isPhone;

    final Widget pill;
    if (phoneRecording) {
      void stop() => _startRecording(context);
      final batch = capture.isPhoneMicBatchRecording;
      final resumable = summary != null && summary.readerPaused && !batch;
      final status = summary == null ? l10n.listening : _pillStatus(summary);
      final healthy = summary == null || summary.healthy;
      pill = HomeControlSurface(
        key: const ValueKey('home_record_pill_stop'),
        semanticsLabel: status,
        semanticsHint: healthy ? l10n.liveTranscript : l10n.moreOptions,
        semanticsActions: _stopping ? null : {CustomSemanticsAction(label: l10n.stopRecording): stop},
        // While the microphone is still starting, the transcript opens by itself when it is up.
        onTap: _stopping || starting
            ? null
            : () {
                OmiHaptics.selection();
                healthy ? _openTranscript(context) : _showCaptureSheet(context, summary);
              },
        child: HomeLivePillContent(
          status: status,
          lastLine: batch ? null : capture.segments.lastOrNull?.text,
          live: summary == null || summary.tone == CaptureTone.live,
          attention: summary?.tone == CaptureTone.attention,
          stopping: _stopping,
          onStop: stop,
          onResume: resumable ? () => _resume(context) : null,
        ),
      );
    } else if ((pendantCapturing || pendantBatch) && !starting && summary != null) {
      final shown = device ?? paired;
      final status = _pillStatus(summary);
      final open = summary.healthy ? () => _openDevice(context) : () => _showCaptureSheet(context, summary);
      pill = HomeControlSurface(
        key: const ValueKey('home_record_pill_device'),
        semanticsLabel: shown == null ? status : '${shown.name}, $status',
        semanticsHint: summary.healthy ? l10n.liveTranscript : l10n.moreOptions,
        onTap: () {
          OmiHaptics.selection();
          open();
        },
        // Holding it offers the phone instead (or a call), as tapping record used to.
        onLongPress: pendantCapturing ? () => _showPendantListening(context) : null,
        longPressHint: pendantCapturing ? l10n.moreOptions : null,
        child: shown == null
            ? HomeLivePillContent(
                status: status,
                live: summary.tone == CaptureTone.live,
                attention: summary.tone == CaptureTone.attention,
                onStop: null,
              )
            : HomeDevicePillContent(
                device: shown,
                status: status,
                live: summary.tone == CaptureTone.live,
                attention: summary.tone == CaptureTone.attention,
                lastLine: summary.batch ? null : capture.segments.lastOrNull?.text,
              ),
      );
    } else if (dropped && paired != null) {
      // The pendant dropped mid-capture: say so here (it reconnects on its own) instead of a card.
      final status =
          '${l10n.disconnected} · ${pendantConnecting ? l10n.reconnecting : l10n.capturePendantDisconnectedShort}';
      pill = HomeControlSurface(
        key: const ValueKey('home_record_pill_dropped'),
        semanticsLabel: '${paired.name}, $status',
        semanticsHint: l10n.moreOptions,
        onTap: () {
          OmiHaptics.selection();
          _showDroppedSheet(context);
        },
        // Holding it records with the phone instead, as + New would.
        onLongPress: () => _startPhoneRecording(context),
        longPressHint: l10n.recordWith,
        child: HomeDevicePillContent(device: paired, status: status, live: false, attention: true),
      );
    } else {
      pill = HomeControlSurface(
        key: const ValueKey('home_record_pill_new'),
        semanticsLabel: l10n.newRecording,
        onTap: starting ? null : () => _startRecording(context),
        onLongPress: canShowOptions ? () => _showRecordOptions(context) : null,
        longPressHint: l10n.moreWaysToRecord,
        child: HomeNewPillContent(starting: starting),
      );
    }

    return KeyedSubtree(
      key: _pillKey,
      child: AnimatedSwitcher(
        duration: OmiMotion.of(context).standard,
        switchInCurve: Curves.easeOut,
        switchOutCurve: Curves.easeIn,
        // Cross-fade with a slight rise, so a change of state reads as the same control updating.
        transitionBuilder: (child, animation) => FadeTransition(
          opacity: animation,
          child: ScaleTransition(scale: Tween(begin: 0.98, end: 1.0).animate(animation), child: child),
        ),
        layoutBuilder: (current, previous) =>
            Stack(alignment: Alignment.center, children: [...previous, if (current != null) current]),
        child: pill,
      ),
    );
  }
}

class SlashLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = OmiColors.danger
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // Position the cross at the bottom right
    final crossSize = size.width * 0.2; // Size of the cross
    final centerX = size.width - crossSize / 2 - 2; // Bottom right positioning
    final centerY = size.height - crossSize / 2 - 2;
    final halfCrossSize = crossSize / 2;

    // Draw the X (cross) - two diagonal lines
    canvas.drawLine(
      Offset(centerX - halfCrossSize, centerY - halfCrossSize),
      Offset(centerX + halfCrossSize, centerY + halfCrossSize),
      paint,
    );

    canvas.drawLine(
      Offset(centerX + halfCrossSize, centerY - halfCrossSize),
      Offset(centerX - halfCrossSize, centerY + halfCrossSize),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Ways to record, opened by holding the home record button. Shown in the shared sheet shell.
class RecordOptionsSheet extends StatelessWidget {
  final VoidCallback onPickPhoneMic;
  final VoidCallback onPickPhoneCall;

  const RecordOptionsSheet({super.key, required this.onPickPhoneMic, required this.onPickPhoneCall});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _RecordOption(
            icon: CaptureSources.icon('phone'),
            title: context.l10n.captureSourcePhoneMic,
            subtitle: context.l10n.recordWithPhoneMicSubtitle,
            onTap: onPickPhoneMic,
          ),
          const SizedBox(height: 10),
          _RecordOption(
            icon: Icons.call_rounded,
            title: context.l10n.phoneCall,
            subtitle: context.l10n.phoneCallSubtitle,
            onTap: onPickPhoneCall,
          ),
        ],
      ),
    );
  }
}

class _RecordOption extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _RecordOption({required this.icon, required this.title, required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: title,
      hint: subtitle,
      excludeSemantics: true,
      child: Material(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.lgAll,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            OmiHaptics.selection();
            onTap();
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.sm),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(shape: BoxShape.circle, color: OmiColors.surface3),
                  child: Icon(icon, color: OmiColors.textPrimary, size: 20),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ),
                ),
                Icon(Icons.chevron_right_rounded, color: OmiColors.textTertiary, size: 22),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A small horizontal battery: outline, nub and a fill proportional to [level]. Neutral unless
/// [critical], when the fill is red.
class BatteryGlyph extends StatelessWidget {
  const BatteryGlyph({super.key, required this.level, required this.critical});

  final int level;
  final bool critical;

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: const Size(20, 10), painter: _BatteryGlyphPainter(level.clamp(0, 100) / 100, critical));
}

class _BatteryGlyphPainter extends CustomPainter {
  _BatteryGlyphPainter(this.fraction, this.critical);
  final double fraction;
  final bool critical;

  @override
  void paint(Canvas canvas, Size size) {
    const nub = 2.0;
    final body = Rect.fromLTWH(0.5, 0.5, size.width - nub - 1.5, size.height - 1);
    canvas.drawRRect(
      RRect.fromRectAndRadius(body, const Radius.circular(2.5)),
      Paint()
        ..color = OmiColors.textSecondary
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(Rect.fromLTWH(body.right + 0.5, size.height / 2 - 2, nub, 4), const Radius.circular(1)),
      Paint()..color = OmiColors.textSecondary,
    );
    final inner = body.deflate(1.75);
    if (fraction <= 0) return;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
          Rect.fromLTWH(inner.left, inner.top, inner.width * fraction, inner.height), const Radius.circular(1)),
      Paint()..color = critical ? OmiColors.danger : OmiColors.textPrimary,
    );
  }

  @override
  bool shouldRepaint(_BatteryGlyphPainter old) => old.fraction != fraction || old.critical != critical;
}

/// Shown when the phone record button is tapped while the pendant is recording: Omi records from
/// one source at a time, so the phone offers to take over (the pendant pauses and resumes after),
/// a call (the pendant pauses during it), or to leave the pendant as it is.
class PendantListeningSheet extends StatelessWidget {
  const PendantListeningSheet({
    super.key,
    required this.onRecordWithPhone,
    required this.onPhoneCall,
    required this.onKeepPendant,
  });

  final VoidCallback onRecordWithPhone;

  /// Null hides the phone-call option.
  final VoidCallback? onPhoneCall;
  final VoidCallback onKeepPendant;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.oneSourceAtATime, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.md),
          _RecordOption(
            icon: CaptureSources.icon('phone'),
            title: l10n.recordWithPhoneInstead,
            subtitle: l10n.pendantPausesUntilYouFinish,
            onTap: onRecordWithPhone,
          ),
          if (onPhoneCall != null) ...[
            const SizedBox(height: 10),
            _RecordOption(
              icon: Icons.call_rounded,
              title: l10n.phoneCall,
              subtitle: l10n.pendantPausesDuringCall,
              onTap: onPhoneCall!,
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
          OmiButton.secondary(label: l10n.keepUsingPendant, onPressed: onKeepPendant),
        ],
      ),
    );
  }
}
