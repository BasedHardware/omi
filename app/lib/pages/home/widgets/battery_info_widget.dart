import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/capture_provider.dart';
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

const _stopGlyphRadius = BorderRadius.all(Radius.circular(4)); // omi-ux-allow: radius-literal -- a glyph

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
                  SizedBox(
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
                  // Only show battery indicator and percentage when battery level is valid (> 0)
                  if (hasBattery) ...[
                    const SizedBox(width: 6.0),
                    // Battery only: a bar glyph, never a coloured dot (live status lives on the
                    // capture card). Red appears only when critically low.
                    if (isCharging) ...[
                      const Icon(Icons.bolt, color: OmiColors.textSecondary, size: 13),
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
              if (!isMemoriesPage) return batteryPill;
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  batteryPill,
                  // 8pt between the painted shapes; the button's 44pt target overhangs
                  // its 36pt circle by 4pt.
                  const SizedBox(width: 4),
                  HeaderCircleButton(
                    semanticLabel: l10n.phoneCallsWithOmi,
                    icon: const Icon(Icons.phone_in_talk_rounded, color: Colors.white, size: 16),
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
                  Text(status, style: OmiType.caption.copyWith(fontSize: 12, color: OmiColors.textSecondary)),
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
                  Image.asset(Assets.images.logoTransparent.path, width: 16, height: 16),
                  // Home has room for the word; the other tabs keep the logo alone (it still has a
                  // spoken label).
                  if (isMemoriesPage) ...[
                    const SizedBox(width: 6),
                    Text(label, style: OmiType.caption.copyWith(fontSize: 12)),
                  ],
                ],
              );
            }
          },
        );
      },
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
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
          child: Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.center, children: children),
        ),
      ),
    );
  }
}

/// Circular phone-mic record button shown to the right of the home chat bar.
/// Tap starts/stops recording; long-press opens the record options sheet (phone call). The options
/// are announced as the long-press action, and a one-time tip points them out after the first
/// recording.
class HomeRecordButton extends StatefulWidget {
  const HomeRecordButton({super.key});

  @override
  State<HomeRecordButton> createState() => _HomeRecordButtonState();
}

class _HomeRecordButtonState extends State<HomeRecordButton> {
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
  static bool _pendantHasCapture(CaptureProvider capture) {
    final source = capture.liveCaptureSource;
    return source != null && source != 'phone' && !SharedPreferencesUtil().batchModeEnabled;
  }

  void _showPendantListening(BuildContext context) {
    OmiHaptics.light();
    showOmiSheet<void>(
      context: context,
      title: context.l10n.pendantIsListeningTitle,
      builder: (sheetContext) => PendantListeningSheet(
        onRecordWithPhone: () {
          Navigator.pop(sheetContext);
          _startPhoneRecording(context);
        },
        onPhoneCall: () {
          Navigator.pop(sheetContext);
          if (context.mounted) routeToPage(context, const PhoneCallsPage());
        },
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
    await captureProvider.streamRecording();
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
        final canShowOptions = !isRecording && !isInitialising;
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
                      decoration: const BoxDecoration(
                        color: OmiColors.textPrimary,
                        borderRadius: _stopGlyphRadius,
                      ),
                    )
                  : isInitialising
                      ? const OmiSpinner(size: OmiSpinnerSize.small)
                      : Container(
                          width: 20,
                          height: 20,
                          decoration: const BoxDecoration(color: OmiColors.textPrimary, shape: BoxShape.circle),
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
                        child: const Icon(Icons.keyboard_arrow_down_rounded, size: 16, color: OmiColors.textPrimary),
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
                  decoration: const BoxDecoration(shape: BoxShape.circle, color: OmiColors.surface3),
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
                const Icon(Icons.chevron_right_rounded, color: OmiColors.textTertiary, size: 22),
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
  final VoidCallback onPhoneCall;
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
          const SizedBox(height: 10),
          _RecordOption(
            icon: Icons.call_rounded,
            title: l10n.phoneCall,
            subtitle: l10n.pendantPausesDuringCall,
            onTap: onPhoneCall,
          ),
          const SizedBox(height: OmiSpacing.md),
          OmiButton.secondary(label: l10n.keepUsingPendant, onPressed: onKeepPendant),
        ],
      ),
    );
  }
}
