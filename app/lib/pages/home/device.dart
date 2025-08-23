import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/device_widget.dart';

import 'package:provider/provider.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'firmware_update.dart';
import '../conversations/sync_page.dart';

class ConnectedDevice extends StatefulWidget {
  const ConnectedDevice({super.key});

  @override
  State<ConnectedDevice> createState() => _ConnectedDeviceState();
}

class _ConnectedDeviceState extends State<ConnectedDevice> {
  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<DeviceProvider>().getDeviceInfo();
    });
    super.initState();
  }

  String _formatStorageInfo(DeviceProvider provider) {
    if (!provider.isDeviceV2Connected) {
      return 'Not Available';
    }

    final totalBytes = provider.captureProvider?.totalStorageFileBytes ?? 0;
    final usedBytes = provider.captureProvider?.totalBytesReceived ?? 0;

    if (totalBytes == 0) {
      return 'Unknown capacity';
    }

    final usedMB = usedBytes / 1024.0 / 1024.0;
    final totalMB = totalBytes / 1024.0 / 1024.0;

    if (usedMB < 1) {
      return '${(usedBytes / 1024.0).toStringAsFixed(1)} KB of ${totalMB.toStringAsFixed(1)} MB used';
    } else {
      return '${usedMB.toStringAsFixed(1)} MB of ${totalMB.toStringAsFixed(1)} MB used';
    }
  }

  IconData _getBatteryIcon(int batteryLevel) {
    if (batteryLevel > 75) {
      return FontAwesomeIcons.batteryFull;
    } else if (batteryLevel > 50) {
      return FontAwesomeIcons.batteryThreeQuarters;
    } else if (batteryLevel > 25) {
      return FontAwesomeIcons.batteryHalf;
    } else if (batteryLevel > 10) {
      return FontAwesomeIcons.batteryQuarter;
    } else {
      return FontAwesomeIcons.batteryEmpty;
    }
  }

  Widget _buildSectionRow(
    String title,
    String value, {
    bool hasArrow = false,
    bool isFirst = false,
    bool isLast = false,
    VoidCallback? onTap,
    bool isRedBackground = false,
  }) {
    final bool isDisabled = onTap == null && !hasArrow && value.isNotEmpty;
    final bool canCopy = value.isNotEmpty && !value.contains('Device must be connected');

    return GestureDetector(
      onTap: onTap ?? (canCopy ? () => _copyToClipboard(value) : null),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        decoration: BoxDecoration(
          color: isRedBackground ? Colors.red.withValues(alpha: 0.1) : null,
          border: Border(
            bottom: isLast
                ? BorderSide.none
                : BorderSide(
                    color: Color(0xFF35343B),
                    width: 0.5,
                  ),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: isRedBackground
                          ? Colors.red.shade300
                          : (onTap == null && !hasArrow && value.contains('Device must be connected'))
                              ? Colors.grey.shade500
                              : Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                  if (value.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      value,
                      style: TextStyle(
                        color: isRedBackground
                            ? Colors.red.shade200
                            : (onTap == null && !hasArrow && value.contains('Device must be connected'))
                                ? Colors.grey.shade500
                                : Colors.white54,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (hasArrow) ...[
              const SizedBox(width: 8),
              Icon(
                Icons.arrow_forward_ios,
                color: isRedBackground ? Colors.red.shade300 : Colors.white54,
                size: 16,
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _copyToClipboard(String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Copied to clipboard: $text'),
        duration: const Duration(seconds: 2),
        backgroundColor: Colors.green,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        body: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: Column(
                children: [
                  const SizedBox(height: 0),
                  // Device Title and Status
                  Column(
                    children: [
                      Text(
                        provider.pairedDevice?.name ?? 'Unknown Device',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 32,
                          fontWeight: FontWeight.bold,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: provider.connectedDevice != null ? Colors.green.withValues(alpha: 0.2) : Colors.grey.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              decoration: BoxDecoration(
                                color: provider.connectedDevice != null ? Colors.green : Colors.grey,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              provider.connectedDevice != null ? 'Connected' : 'Offline',
                              style: TextStyle(
                                color: provider.connectedDevice != null ? Colors.green : Colors.grey,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  DeviceAnimationWidget(
                    isConnected: provider.connectedDevice != null,
                    deviceName: provider.connectedDevice?.name ?? provider.pairedDevice?.name,
                    animatedBackground: provider.connectedDevice != null,
                  ),

                  const SizedBox(height: 8),
                  // Device Details Section
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Battery Level Section
                        if (provider.connectedDevice != null)
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1F1F25),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Row(
                              children: [
                                FaIcon(
                                  _getBatteryIcon(provider.batteryLevel),
                                  color: provider.batteryLevel > 75
                                      ? const Color.fromARGB(255, 0, 255, 8)
                                      : provider.batteryLevel > 20
                                          ? Colors.yellow.shade700
                                          : Colors.red,
                                  size: 20,
                                ),
                                const SizedBox(width: 12),
                                const Text(
                                  'Battery Level',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const Spacer(),
                                Text(
                                  '${provider.batteryLevel}%',
                                  style: const TextStyle(
                                    color: Colors.white54,
                                    fontSize: 16,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        if (provider.connectedDevice != null) const SizedBox(height: 20),

                        // Controllable Items Section
                        Container(
                          decoration: BoxDecoration(
                            color: const Color(0xFF1F1F25),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Column(
                            children: [
                              _buildSectionRow(
                                'Product Update',
                                provider.connectedDevice == null ? 'Device must be connected' : '',
                                hasArrow: provider.connectedDevice != null,
                                isFirst: true,
                                onTap: provider.connectedDevice != null
                                    ? () {
                                        Navigator.of(context).push(
                                          MaterialPageRoute(
                                            builder: (context) => FirmwareUpdate(device: provider.pairedDevice),
                                          ),
                                        );
                                      }
                                    : null,
                              ),
                              if (provider.isDeviceV2Connected)
                                _buildSectionRow(
                                  'SD Card Sync',
                                  'Import audio files from SD Card',
                                  hasArrow: true,
                                  onTap: () {
                                    Navigator.of(context).push(
                                      MaterialPageRoute(
                                        builder: (context) => const SyncPage(),
                                      ),
                                    );
                                  },
                                ),
                              _buildSectionRow(
                                'Issues charging the device?',
                                'Tap to see the guide',
                                hasArrow: true,
                                onTap: () async {
                                  await IntercomManager.instance.displayChargingArticle(provider.pairedDevice?.name ?? 'DevKit1');
                                },
                              ),
                              _buildSectionRow(
                                provider.connectedDevice == null ? 'Unpair' : 'Disconnect',
                                '',
                                hasArrow: true,
                                isLast: true,
                                isRedBackground: true,
                                onTap: () async {
                                  await SharedPreferencesUtil().btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0));
                                  SharedPreferencesUtil().deviceName = '';
                                  if (provider.connectedDevice != null) {
                                    await _bleDisconnectDevice(provider.connectedDevice!);
                                  }
                                  if (context.mounted) {
                                    context.read<DeviceProvider>().setIsConnected(false);
                                    context.read<DeviceProvider>().setConnectedDevice(null);
                                    context.read<DeviceProvider>().updateConnectingStatus(false);
                                    Navigator.of(context).pop();
                                  }
                                  MixpanelManager().disconnectFriendClicked();
                                },
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 20),

                        // Info Only Section
                        Container(
                          decoration: BoxDecoration(
                            color: const Color(0xFF1F1F25),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Column(
                            children: [
                              _buildSectionRow(
                                'Product Name',
                                provider.pairedDevice?.name ?? 'Unknown Device',
                                hasArrow: false,
                                isFirst: true,
                              ),
                              _buildSectionRow(
                                'Model Number',
                                provider.pairedDevice?.modelNumber ?? 'Unknown',
                                hasArrow: false,
                              ),
                              _buildSectionRow(
                                'Manufacturer Name',
                                provider.pairedDevice?.manufacturerName ?? 'Unknown',
                                hasArrow: false,
                              ),
                              _buildSectionRow(
                                'Firmware Version',
                                provider.pairedDevice?.firmwareRevision ?? 'Unknown',
                                hasArrow: false,
                              ),
                              _buildSectionRow(
                                'Device ID',
                                provider.pairedDevice?.id ?? 'Unknown',
                                hasArrow: false,
                              ),
                              _buildSectionRow(
                                'Serial Number',
                                provider.pairedDevice?.id.replaceAll(':', '').replaceAll('-', '').toUpperCase() ?? 'Unknown',
                                hasArrow: false,
                              ),
                              if (provider.isDeviceV2Connected)
                                _buildSectionRow(
                                  'Storage',
                                  _formatStorageInfo(provider),
                                  hasArrow: false,
                                  isLast: true,
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 64), // Extra padding to ensure scrollable content
                ],
              ),
            ),
          ],
        ),
      );
    });
  }
}
