import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/device_widget.dart';

/// Top of the device page: the device's name, a Connected / Disconnected pill and its picture.
class DevicePageHeader extends StatelessWidget {
  const DevicePageHeader({super.key, required this.pairedDevice, required this.connectedDevice});

  final BtDevice? pairedDevice;
  final BtDevice? connectedDevice;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isConnected = connectedDevice != null;
    final stateColor = isConnected ? OmiColors.success : OmiColors.textSecondary;
    return Column(
      children: [
        Semantics(
          header: true,
          child: Text(
            pairedDevice?.name ?? l10n.unknownDevice,
            style: OmiType.title1,
            textAlign: TextAlign.center,
          ),
        ),
        const SizedBox(height: OmiSpacing.sm),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
          decoration: BoxDecoration(
            color: isConnected ? OmiColors.successSurface : OmiColors.surface2,
            borderRadius: OmiRadius.pillAll,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(color: stateColor, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Text(
                isConnected ? l10n.connected : l10n.disconnected,
                style: OmiType.footnote.copyWith(color: stateColor, fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        // The pulsing background only runs while the device is connected, and never under
        // Reduce Motion; muting the ticker also stops it scheduling frames when it is hidden.
        ExcludeSemantics(
          child: TickerMode(
            enabled: isConnected && !MediaQuery.disableAnimationsOf(context),
            child: DeviceAnimationWidget(
              sizeMultiplier: 0.7,
              deviceType: connectedDevice?.type,
              modelNumber: connectedDevice?.modelNumber,
              isConnected: isConnected,
              deviceName: connectedDevice?.name ?? pairedDevice?.name,
              animatedBackground: isConnected,
            ),
          ),
        ),
      ],
    );
  }
}

/// The battery row: level (or "Charging") with a level-coloured icon.
class DeviceBatteryGroup extends StatelessWidget {
  const DeviceBatteryGroup({super.key, required this.batteryLevel, required this.isCharging});

  final int batteryLevel;
  final bool isCharging;

  FaIconData get _icon {
    if (batteryLevel > 75) return FontAwesomeIcons.batteryFull;
    if (batteryLevel > 50) return FontAwesomeIcons.batteryThreeQuarters;
    if (batteryLevel > 25) return FontAwesomeIcons.batteryHalf;
    if (batteryLevel > 10) return FontAwesomeIcons.batteryQuarter;
    return FontAwesomeIcons.batteryEmpty;
  }

  Color get _color {
    if (batteryLevel > 75) return OmiColors.success;
    if (batteryLevel > 20) return OmiColors.warning;
    return OmiColors.danger;
  }

  @override
  Widget build(BuildContext context) {
    return OmiSettingsGroup(
      children: [
        OmiSettingsRow(
          leading: isCharging
              ? const FaIcon(FontAwesomeIcons.chargingStation, color: OmiColors.success)
              : FaIcon(_icon, color: _color),
          title: isCharging ? context.l10n.charging : context.l10n.batteryLevel,
          value: '$batteryLevel%',
        ),
      ],
    );
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
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
            child: const Center(
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
        const FaIcon(FontAwesomeIcons.bluetooth, color: OmiColors.textTertiary, size: 14),
        const SizedBox(width: 6),
        Text(context.l10n.dataRateKbps(bleReceiveKbps.toStringAsFixed(1)), style: style),
        const SizedBox(width: OmiSpacing.xl),
        const FaIcon(FontAwesomeIcons.signal, color: OmiColors.textTertiary, size: 14),
        const SizedBox(width: 6),
        Text(context.l10n.dataRateKbps(wsSendKbps.toStringAsFixed(1)), style: style),
      ],
    );
  }
}
