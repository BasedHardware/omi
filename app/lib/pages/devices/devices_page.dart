import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/meta_wearables/meta_glasses_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/meta_wearables_device_label.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Multi-device hub: every device linked to Omi in one place — the BLE
/// wearable (Omi, pendant, watch, ...) from [DeviceProvider] and each pair of
/// Meta glasses from [MetaWearablesProvider] — with per-device status and
/// navigation into the device-specific pages.
class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<MetaWearablesProvider>().init();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        leading: Padding(
          padding: const EdgeInsets.only(left: 12),
          child: GestureDetector(
            onTap: () => Navigator.of(context).pop(),
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
              child: const Icon(FontAwesomeIcons.chevronLeft, size: 16, color: Colors.white70),
            ),
          ),
        ),
        title: Text(
          context.l10n.myDevices,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        centerTitle: true,
      ),
      body: Consumer2<DeviceProvider, MetaWearablesProvider>(
        builder: (context, deviceProvider, metaProvider, child) {
          final bleDevice = deviceProvider.pairedDevice;
          final hasBleDevice = bleDevice != null && bleDevice.id.isNotEmpty;
          final glassesConnected = metaProvider.isRegistered && metaProvider.hasDevices;
          return ListView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            children: [
              if (hasBleDevice) _bleDeviceCard(context, deviceProvider, bleDevice),
              if (glassesConnected) ...metaProvider.devices.map((d) => _glassesCard(context, metaProvider, d)),
              const SizedBox(height: 8),
              _connectDeviceCard(context),
            ],
          );
        },
      ),
    );
  }

  Widget _card({required Widget leading, required Widget body, Widget? trailing, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(color: ResponsiveHelper.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            leading,
            const SizedBox(width: 12),
            Expanded(child: body),
            if (trailing != null) trailing,
            const SizedBox(width: 8),
            const Icon(FontAwesomeIcons.chevronRight, size: 14, color: Colors.white38),
          ],
        ),
      ),
    );
  }

  Widget _bleDeviceCard(BuildContext context, DeviceProvider deviceProvider, BtDevice device) {
    final connected = deviceProvider.isConnected;
    final battery = deviceProvider.batteryLevel;
    return _card(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ConnectedDevice())),
      leading: Image.asset(
        DeviceUtils.getDeviceImagePathWithState(
          deviceType: device.type,
          modelNumber: device.modelNumber,
          deviceName: device.name,
          isConnected: connected,
        ),
        width: 36,
        height: 36,
        fit: BoxFit.contain,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            device.name.isNotEmpty ? device.name : 'Omi',
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
          ),
          Text(
            connected ? context.l10n.connected : context.l10n.disconnected,
            style: TextStyle(color: connected ? Colors.greenAccent : Colors.white54, fontSize: 12),
          ),
        ],
      ),
      trailing: connected && battery > 0
          ? Text('$battery%', style: const TextStyle(color: Colors.white70, fontSize: 13))
          : null,
    );
  }

  Widget _glassesCard(BuildContext context, MetaWearablesProvider metaProvider, DeviceInfo device) {
    final selected = metaProvider.isSelected(device);
    final linked = device.linkState == DeviceLinkState.connected || device.linkState == DeviceLinkState.unknown;
    final capturing = metaProvider.isCapturing && selected && linked;
    final needsUpdate = metaProvider.hasCompatibilityUpdateAction(device);
    final healthStatus = _metaGlassesHealthText(context, metaProvider.health);
    final String status;
    final Color statusColor;
    if (healthStatus != null) {
      status = healthStatus;
      statusColor = Colors.orangeAccent;
    } else if (capturing) {
      status = context.l10n.listening;
      statusColor = Colors.redAccent;
    } else if (linked) {
      status = context.l10n.connected;
      statusColor = Colors.greenAccent;
    } else if (device.linkState == DeviceLinkState.connecting) {
      status = context.l10n.searching;
      statusColor = Colors.white54;
    } else {
      status = context.l10n.metaGlassesPairInMetaAI;
      statusColor = Colors.orangeAccent;
    }
    return _card(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const MetaGlassesPage())),
      leading: Image.asset(Assets.images.omiGlass.path, width: 36, height: 36, fit: BoxFit.contain),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            device.name.isNotEmpty ? device.name : context.l10n.metaGlasses,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
          ),
          Text(
            metaWearablesDeviceKindLabel(context.l10n, device.kind),
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
          Text(status, style: TextStyle(color: statusColor, fontSize: 12)),
          if (needsUpdate)
            Text(
              context.l10n.firmwareUpdateAvailable,
              style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
            ),
        ],
      ),
      trailing: selected || needsUpdate
          ? Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (needsUpdate)
                  TextButton(
                    onPressed: () => metaProvider.openCompatibilityUpdate(device),
                    style: TextButton.styleFrom(
                      foregroundColor: Colors.orangeAccent,
                      minimumSize: Size.zero,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                    child: Text(context.l10n.update),
                  ),
                if (selected) const Icon(Icons.check_circle, color: Colors.white, size: 18),
              ],
            )
          : null,
    );
  }

  String? _metaGlassesHealthText(BuildContext context, MetaGlassesHealth health) {
    switch (health) {
      case MetaGlassesHealth.ok:
        return null;
      case MetaGlassesHealth.overheating:
        return context.l10n.metaGlassesOverheating;
      case MetaGlassesHealth.foldedClosed:
        return context.l10n.metaGlassesFolded;
    }
  }

  Widget _connectDeviceCard(BuildContext context) {
    return _card(
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (context) => const ConnectDevicePage())),
      leading: Container(
        width: 36,
        height: 36,
        decoration: const BoxDecoration(color: Color(0xFF1F1F25), shape: BoxShape.circle),
        child: const Icon(Icons.add, color: Colors.white70, size: 20),
      ),
      body: Text(
        context.l10n.connectAnotherDevice,
        style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
      ),
    );
  }
}
