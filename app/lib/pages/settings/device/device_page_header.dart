import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/device_widget.dart';

/// The device page hero (v2 `Device.dc`): the device on a recessed panel, with its live state and
/// battery on glass chips along the bottom. The Omi pendant hangs from its cord (LED lit while
/// connected); other devices show their photo.
class DeviceHeroCard extends StatelessWidget {
  const DeviceHeroCard({
    super.key,
    required this.pairedDevice,
    required this.connectedDevice,
    this.isConnecting = false,
    this.isReceivingAudio = false,
    this.batteryLevel = -1,
    this.isCharging = false,
  });

  final BtDevice? pairedDevice;
  final BtDevice? connectedDevice;
  final bool isConnecting;

  /// This device is the live source and audio is arriving from it.
  final bool isReceivingAudio;

  /// Percent, or below 1 when unknown (no chip).
  final int batteryLevel;
  final bool isCharging;

  /// The same rule the device photo follows: an Omi that is not a dev kit or Glass is the pendant.
  bool get _isOmiPendant {
    final device = connectedDevice ?? pairedDevice;
    if (device?.type != DeviceType.omi) return false;
    final path = DeviceUtils.getDeviceImagePath(
      deviceType: device!.type,
      modelNumber: device.modelNumber,
      deviceName: device.name,
    );
    return path == Assets.images.omiWithoutRope.path || path == Assets.images.omiWithRope.path;
  }

  /// Horizontal battery glyphs, like the design's.
  FaIconData get _batteryIcon {
    if (isCharging) return FontAwesomeIcons.batteryFull;
    if (batteryLevel > 75) return FontAwesomeIcons.batteryFull;
    if (batteryLevel > 50) return FontAwesomeIcons.batteryThreeQuarters;
    if (batteryLevel > 25) return FontAwesomeIcons.batteryHalf;
    if (batteryLevel > 10) return FontAwesomeIcons.batteryQuarter;
    return FontAwesomeIcons.batteryEmpty;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isConnected = connectedDevice != null;
    // Blue is the live microphone only; a device that is connected but not sending audio is green.
    final (dot, status) = switch ((isConnected, isReceivingAudio, isConnecting)) {
      (true, true, _) => (OmiColors.live, '${l10n.connected} · ${l10n.listening}'),
      (true, false, _) => (OmiColors.success, l10n.connected),
      (false, _, true) => (OmiColors.textTertiary, l10n.deviceConnecting),
      _ => (OmiColors.textTertiary, l10n.disconnected),
    };
    final lowBattery = !isCharging && batteryLevel <= 20;
    return Container(
      height: 250,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(color: OmiColors.well, borderRadius: OmiRadius.cardLargeAll),
      child: Stack(
        children: [
          Positioned.fill(
            child: _isOmiPendant
                ? OmiPendantInCard(lit: isConnected)
                // The pulsing background only runs while the device is connected, and never under
                // Reduce Motion; muting the ticker also stops it scheduling frames when it is hidden.
                : Padding(
                    padding: const EdgeInsets.only(bottom: 40),
                    child: ExcludeSemantics(
                      child: TickerMode(
                        enabled: isConnected && !MediaQuery.disableAnimationsOf(context),
                        child: DeviceAnimationWidget(
                          sizeMultiplier: 0.55,
                          deviceType: connectedDevice?.type ?? pairedDevice?.type,
                          modelNumber: connectedDevice?.modelNumber ?? pairedDevice?.modelNumber,
                          isConnected: isConnected,
                          deviceName: connectedDevice?.name ?? pairedDevice?.name,
                          animatedBackground: false,
                        ),
                      ),
                    ),
                  ),
          ),
          Positioned(
            left: 14,
            right: 14,
            bottom: 14,
            child: Row(
              children: [
                Flexible(
                  child: _GlassChip(
                    key: const ValueKey('device_hero_status'),
                    children: [
                      Container(
                        width: 7,
                        height: 7,
                        decoration: BoxDecoration(
                          color: dot,
                          shape: BoxShape.circle,
                          boxShadow: isReceivingAudio && isConnected
                              ? [BoxShadow(color: dot.withValues(alpha: 0.9), blurRadius: 6)]
                              : null,
                        ),
                      ),
                      const SizedBox(width: 7),
                      Flexible(child: Text(status, maxLines: 1, overflow: TextOverflow.ellipsis)),
                    ],
                  ),
                ),
                if (isConnected && batteryLevel > 0) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  const Spacer(),
                  _GlassChip(
                    key: const ValueKey('device_hero_battery'),
                    semanticsLabel: '${isCharging ? l10n.charging : l10n.batteryLevel} $batteryLevel%',
                    children: [
                      if (isCharging) ...[
                        FaIcon(FontAwesomeIcons.bolt, size: 11, color: OmiColors.success),
                        const SizedBox(width: 4),
                      ],
                      FaIcon(_batteryIcon, size: 14, color: lowBattery ? OmiColors.danger : OmiColors.textPrimary),
                      const SizedBox(width: 6),
                      Text('$batteryLevel%'),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A 32pt glass capsule with 13pt semibold text (the hero's status and battery chips).
class _GlassChip extends StatelessWidget {
  const _GlassChip({super.key, required this.children, this.semanticsLabel});

  final List<Widget> children;
  final String? semanticsLabel;

  @override
  Widget build(BuildContext context) {
    final chip = OmiGlass(
      borderRadius: OmiRadius.pillAll,
      child: Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
        child: DefaultTextStyle.merge(
          style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w600),
          child: Row(mainAxisSize: MainAxisSize.min, children: children),
        ),
      ),
    );
    if (semanticsLabel == null) return chip;
    return Semantics(label: semanticsLabel, excludeSemantics: true, child: chip);
  }
}

/// Shown instead of the device controls while the device is not connected.
class DeviceDisconnectedCard extends StatelessWidget {
  const DeviceDisconnectedCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.xxl),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
            child: Center(
              child: FaIcon(FontAwesomeIcons.linkSlash, color: OmiColors.textTertiary, size: 24),
            ),
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.deviceNotConnected, style: OmiType.headline, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            context.l10n.connectDeviceMessage,
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
          ),
        ],
      ),
    );
  }
}

/// Live Bluetooth-in / network-out data rates, shown while the device is streaming audio.
class DeviceStreamingMetrics extends StatelessWidget {
  const DeviceStreamingMetrics({super.key, required this.bleReceiveKbps, required this.wsSendKbps});

  final double bleReceiveKbps;
  final double wsSendKbps;

  @override
  Widget build(BuildContext context) {
    final style = OmiType.subhead.copyWith(color: OmiColors.textTertiary);
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        FaIcon(FontAwesomeIcons.bluetooth, color: OmiColors.textTertiary, size: 14),
        const SizedBox(width: 6),
        Text(context.l10n.dataRateKbps(bleReceiveKbps.toStringAsFixed(1)), style: style),
        const SizedBox(width: OmiSpacing.xl),
        FaIcon(FontAwesomeIcons.signal, color: OmiColors.textTertiary, size: 14),
        const SizedBox(width: 6),
        Text(context.l10n.dataRateKbps(wsSendKbps.toStringAsFixed(1)), style: style),
      ],
    );
  }
}
