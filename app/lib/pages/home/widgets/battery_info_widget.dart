import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/devices/recording_source_sheet.dart';
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
                  PlatformManager.instance.analytics.batteryIndicatorClicked();
                  showRecordingSourceSheet(context);
                },
                children: [
                  _DeviceThumb(
                    path: DeviceUtils.getDeviceImagePath(
                      deviceType: connectedDevice.type,
                      modelNumber: connectedDevice.modelNumber,
                      deviceName: connectedDevice.name,
                    ),
                    lit: true,
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
                      style: OmiType.subhead.copyWith(
                        fontWeight: FontWeight.w700,
                        color: low ? OmiColors.danger : OmiColors.textPrimary,
                      ),
                    ),
                  ],
                ],
              );
              // Rev 3: the chip is the source; calls live in Settings → Devices → Phone Calls.
              return batteryPill;
            } else if (pairedDevice != null && pairedDevice.id.isNotEmpty) {
              // Paired but not connected: "Connecting…" while a reconnect runs, otherwise one word,
              // "Disconnected" (the device page uses the same word).
              final status = isConnecting ? l10n.deviceConnecting : l10n.disconnected;
              return _DevicePill(
                semanticsLabel: '${pairedDevice.name}, $status',
                onTap: () => showRecordingSourceSheet(context),
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
                onTap: () {
                  if (SharedPreferencesUtil().btDevice.id.isEmpty) {
                    PlatformManager.instance.analytics.connectFriendClicked();
                  }
                  showRecordingSourceSheet(context);
                },
                children: [
                  Image.asset(Assets.images.logoTransparent.path, width: 16, height: 16, color: OmiColors.textPrimary),
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
        // v2: a 44pt glass pill (the device, its battery) on the leading edge of Home.
        child: OmiGlass(
          borderRadius: OmiRadius.pillAll,
          child: Container(
            height: OmiSize.minTap,
            padding: const EdgeInsets.only(left: 6, right: OmiSpacing.sm),
            child:
                Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.center, children: children),
          ),
        ),
      ),
    );
  }
}

/// Recording with this phone (Today's Start listening, Recording from → This phone, Devices →
/// "Use this phone"). An Omi call opens instead; a wearable that is listening asks first (one
/// source records at a time); a phone recording that is already running is finished.
abstract final class PhoneCapture {
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

  static void _showPendantListening(BuildContext context) {
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

  static Future<void> start(BuildContext context) async {
    final captureProvider = context.read<CaptureProvider>();
    if (captureProvider.recordingState == RecordingState.initialising) return;
    // An Omi call owns the capture while it runs: open the call, never a recording.
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

  static Future<void> _startPhoneRecording(BuildContext context) async {
    final captureProvider = context.read<CaptureProvider>();
    OmiHaptics.medium();
    if (captureProvider.recordingState == RecordingState.record || captureProvider.isPhoneMicPaused) {
      // A phone recording is running: finish it (processed, except Transcribe Later,
      // whose local file is finalized on stop), then any pendant it paused resumes.
      await captureProvider.finishCapture();
      PlatformManager.instance.analytics.phoneMicRecordingStopped();
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

/// One choice in [PendantListeningSheet]: a round icon, a title and what it does.
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
                OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
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

/// The device in the pill: the Omi pendant is drawn (LED lit while connected); other devices use
/// their photo.
class _DeviceThumb extends StatelessWidget {
  const _DeviceThumb({required this.path, required this.lit});

  final String path;
  final bool lit;

  @override
  Widget build(BuildContext context) {
    final pendant = path == Assets.images.omiWithoutRope.path || path == Assets.images.omiWithRope.path;
    // The LED is blue only while this device is what Omi is recording from.
    final recording = context.select<CaptureProvider, bool>((c) => c.recordingState == RecordingState.deviceRecord);
    return SizedBox.square(
      dimension: 32,
      child: pendant
          ? Center(child: OmiOrb(size: 30, live: lit && recording))
          : Padding(padding: const EdgeInsets.all(6), child: Image.asset(path, fit: BoxFit.contain)),
    );
  }
}
