import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// About (v2 `Device.dc`): what the device reports about itself — model, firmware, serial number,
/// then the id and hardware details support asks for. Each known value copies on tap; unknown
/// values show "Unknown" and do nothing.
///
/// For Ray-Ban Meta glasses the firmware row is replaced by microphone and camera readiness
/// ([rayBanCameraStatus] resolves to 'granted', 'unavailable' or another permission state).
class DeviceInfoGroups extends StatelessWidget {
  const DeviceInfoGroups({
    super.key,
    required this.pairedDevice,
    required this.isDeviceConnected,
    this.rayBanCameraStatus,
  });

  final BtDevice? pairedDevice;
  final bool isDeviceConnected;
  final Future<String>? rayBanCameraStatus;

  static String _truncate(String value) {
    if (value.length > 12) return '${value.substring(0, 5)}•••${value.substring(value.length - 4)}';
    return value;
  }

  Widget _copyRow(
    BuildContext context, {
    required String title,
    required String? value,
    bool truncate = false,
  }) {
    final unknown = context.l10n.unknown;
    // BtDevice reports a missing GATT value as the English word 'Unknown'.
    final known = value != null && value.isNotEmpty && value != 'Unknown';
    return OmiSettingsRow(
      title: title,
      value: known ? (truncate ? _truncate(value) : value) : unknown,
      showChevron: false,
      onTap: known ? () => OmiClipboard.copy(context, value, what: title) : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final device = pairedDevice;
    final deviceId = device?.id;
    final normalizedId = deviceId?.replaceAll(':', '').replaceAll('-', '').toUpperCase();
    final serialNumber = device?.serialNumber ?? normalizedId;
    // Hide the serial number when it is the device id again (raw or normalized), so two rows
    // never look identical.
    final showSerialNumber =
        serialNumber != null && serialNumber.isNotEmpty && serialNumber != normalizedId && serialNumber != deviceId;
    final isRayBan = device?.type == DeviceType.raybanMeta;

    return OmiSettingsGroup(
      header: l10n.about,
      children: [
        _copyRow(context, title: l10n.model, value: device?.modelNumber),
        if (isRayBan) ...[
          OmiSettingsRow(
            title: l10n.microphone,
            value: isDeviceConnected ? l10n.raybanMetaMicrophoneReady : l10n.disconnected,
          ),
          FutureBuilder<String>(
            future: rayBanCameraStatus,
            builder: (context, snapshot) {
              final status = snapshot.data;
              final String label;
              if (status == 'granted') {
                label = l10n.raybanMetaImageCaptureReady;
              } else if (status == 'unavailable') {
                label = l10n.raybanMetaImageCaptureUnavailable;
              } else {
                label = l10n.raybanMetaAllowCamera;
              }
              return OmiSettingsRow(title: l10n.raybanMetaCamera, value: snapshot.hasData ? label : null);
            },
          ),
        ] else
          _copyRow(context, title: l10n.firmware, value: device?.firmwareRevision),
        if (showSerialNumber) _copyRow(context, title: l10n.serialNumber, value: serialNumber, truncate: true),
        _copyRow(context, title: l10n.deviceId, value: deviceId, truncate: true),
        _copyRow(context, title: l10n.hardwareRevision, value: device?.hardwareRevision),
        _copyRow(context, title: l10n.manufacturer, value: device?.manufacturerName),
      ],
    );
  }
}
