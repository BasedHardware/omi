import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The sources that can listen right now: the paired wearable (when there is one) and this
/// phone's microphone, each with its real state. Settings → Devices (Home's Manage devices).
class DeviceSourcesGroup extends StatelessWidget {
  const DeviceSourcesGroup({super.key, this.onDeviceTap, this.onUsePhone});

  /// Tapping the paired wearable; opens its page by default.
  final VoidCallback? onDeviceTap;

  /// Tapping this phone while it is not the live source (switch to it). Without it the phone row
  /// only reports its state.
  final VoidCallback? onUsePhone;

  /// "Connected · 42 %", "Connecting…", "Disconnected", or "Syncing" while its recordings upload.
  static String _pairedStatus(BuildContext context, DeviceProvider devices, SyncProvider sync) {
    final l10n = context.l10n;
    if (devices.isConnecting) return l10n.deviceConnecting;
    if (!devices.isConnected) return l10n.disconnected;
    if (sync.isSyncing) return l10n.syncingStatus;
    final battery = devices.batteryLevel;
    return battery > 0 ? '${l10n.connected} · $battery%' : l10n.connected;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer3<DeviceProvider, CaptureProvider, SyncProvider>(
      builder: (context, devices, capture, sync, _) {
        final paired = devices.pairedDevice;
        final hasPaired = paired != null && paired.id.isNotEmpty;
        final deviceLive = devices.isConnected && capture.recordingState == RecordingState.deviceRecord;
        final phoneLive = capture.recordingState == RecordingState.record || capture.isPhoneMicPaused;
        final starting = capture.recordingState == RecordingState.initialising;
        final usePhone = onUsePhone;
        return OmiSettingsGroup(
          children: [
            if (hasPaired)
              OmiSettingsRow(
                key: const Key('devices_paired_device'),
                leading: _DeviceImage(device: paired),
                title: paired.name,
                subtitle: _pairedStatus(context, devices, sync),
                trailing: _StatusBadge(
                  label: deviceLive ? l10n.live : l10n.deviceReady,
                  live: deviceLive,
                  visible: devices.isConnected,
                ),
                showChevron: true,
                onTap: onDeviceTap ?? () => routeToPage(context, const ConnectedDevice()),
              ),
            OmiSettingsRow(
              key: const Key('devices_this_phone'),
              leading: const OmiGlyph(OmiGlyphs.iphone),
              title: PlatformService.isIOS ? l10n.memoryThisIphone : l10n.memoryThisPhone,
              subtitle: l10n.microphone,
              trailing: _StatusBadge(label: phoneLive ? l10n.live : l10n.deviceReady, live: phoneLive),
              showChevron: false,
              onTap: usePhone == null || phoneLive || starting
                  ? null
                  : () {
                      OmiHaptics.selection();
                      usePhone();
                    },
            ),
          ],
        );
      },
    );
  }
}

/// The product's own picture, sized like a row icon.
class _DeviceImage extends StatelessWidget {
  const _DeviceImage({required this.device});

  final BtDevice device;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        width: 30,
        height: 30,
        child: Image.asset(DeviceUtils.getDeviceImageFromBtDevice(device), fit: BoxFit.contain),
      ),
    );
  }
}

/// "Live" in the LED blue with its dot while this is the source being recorded (blue only means
/// the mic is on); "Ready" in quiet grey otherwise.
class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.live, this.visible = true});

  final String label;
  final bool live;
  final bool visible;

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    final color = live ? OmiColors.live : OmiColors.textSecondary;
    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: live ? OmiColors.live.withValues(alpha: 0.14) : OmiColors.surface2,
        borderRadius: OmiRadius.pillAll,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (live) ...[
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(color: OmiColors.live, shape: BoxShape.circle),
            ),
            const SizedBox(width: 6),
          ],
          Text(label, style: OmiType.caption1.copyWith(fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }
}
