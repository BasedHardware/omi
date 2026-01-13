import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices/companion_device_manager.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../conversations/sync_page.dart';
import 'firmware_update.dart';

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

  Future _bleUnpairDevice(BtDevice btDevice) async {
    if (PlatformService.isAndroid) {
      try {
        final companionService = CompanionDeviceManagerService.instance;
        await companionService.stopObservingDevicePresence(btDevice.id);
        await companionService.disassociate(btDevice.id);
      } catch (e) {
        debugPrint('CompanionDevice: Error disassociating during unpair: $e');
      }
    }

    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    await connection.unpair();
    return await connection.disconnect();
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await context.read<DeviceProvider>().getDeviceInfo();
    });
    super.initState();
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

  Color _getBatteryColor(int batteryLevel) {
    if (batteryLevel > 75) {
      return const Color.fromARGB(255, 0, 255, 8);
    } else if (batteryLevel > 20) {
      return Colors.yellow.shade700;
    } else {
      return Colors.red;
    }
  }

  void _copyToClipboard(String title, String text) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$title copied to clipboard')),
    );
  }

  Widget _buildProfileStyleItem({
    required IconData icon,
    required String title,
    String? chipValue,
    String? copyValue,
    VoidCallback? onTap,
    bool showChevron = true,
    Color? iconColor,
    Color? titleColor,
    Color? chipColor,
    Color? chipTextColor,
  }) {
    final content = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      child: Row(
        children: [
          SizedBox(
            width: 24,
            height: 24,
            child: Padding(
              padding: const EdgeInsets.only(left: 2, top: 1),
              child: FaIcon(icon, color: iconColor ?? const Color(0xFF8E8E93), size: 20),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              title,
              style: TextStyle(
                color: titleColor ?? Colors.white,
                fontSize: 17,
                fontWeight: FontWeight.w400,
              ),
            ),
          ),
          if (chipValue != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: chipColor ?? const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                chipValue,
                style: TextStyle(
                  color: chipTextColor ?? Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            if (showChevron) const SizedBox(width: 8),
          ],
          if (showChevron)
            const Icon(
              Icons.chevron_right,
              color: Color(0xFF3C3C43),
              size: 20,
            ),
        ],
      ),
    );

    if (copyValue != null) {
      return GestureDetector(
        onTap: () => _copyToClipboard(title, copyValue),
        child: content,
      );
    }

    if (onTap != null) {
      return GestureDetector(onTap: onTap, child: content);
    }
    return content;
  }

  Widget _buildBatterySection(DeviceProvider provider) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
        child: Row(
          children: [
            SizedBox(
              width: 24,
              height: 24,
              child: Padding(
                padding: const EdgeInsets.only(left: 2, top: 1),
                child: FaIcon(
                  _getBatteryIcon(provider.batteryLevel),
                  color: _getBatteryColor(provider.batteryLevel),
                  size: 20,
                ),
              ),
            ),
            const SizedBox(width: 16),
            const Expanded(
              child: Text(
                'Battery Level',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(100),
              ),
              child: Text(
                '${provider.batteryLevel}%',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActionsSection(DeviceProvider provider) {
    final syncProvider = context.watch<SyncProvider>();
    final pendingSeconds = syncProvider.missingWalsInSeconds;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Firmware Update
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.download,
            title: 'Product Update',
            chipValue: provider.connectedDevice == null
                ? 'Offline'
                : provider.havingNewFirmware
                    ? 'Available'
                    : null,
            onTap: provider.connectedDevice != null
                ? () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (context) => FirmwareUpdate(device: provider.pairedDevice),
                      ),
                    );
                  }
                : null,
            showChevron: provider.connectedDevice != null,
          ),
          // SD Card Sync
          if (provider.isDeviceStorageSupport) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildProfileStyleItem(
              icon: FontAwesomeIcons.sdCard,
              title: 'SD Card Sync',
              chipValue: pendingSeconds > 0 ? secondsToCompactDuration(pendingSeconds) : null,
              chipColor: pendingSeconds > 0 ? const Color(0xFF3D3520) : null,
              chipTextColor: pendingSeconds > 0 ? const Color(0xFFFFD060) : null,
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const SyncPage(),
                  ),
                );
              },
            ),
          ],
          // Charging Issues
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          GestureDetector(
            onTap: () async {
              if (PlatformService.isIntercomSupported) {
                await IntercomManager.instance.displayChargingArticle(provider.pairedDevice?.name ?? 'DevKit1');
              } else {
                final deviceName = provider.pairedDevice?.name ?? 'DevKit1';
                String url;
                if (deviceName == 'Omi DevKit 2') {
                  url = 'https://www.omi.me/pages/charging-devkit2';
                } else if (deviceName == 'Omi') {
                  url = 'https://www.omi.me/pages/charging-omi';
                } else {
                  url = 'https://www.omi.me/pages/charging';
                }
                final uri = Uri.parse(url);
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              }
            },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
              child: Row(
                children: [
                  const SizedBox(
                    width: 24,
                    height: 24,
                    child: Padding(
                      padding: EdgeInsets.only(left: 2, top: 1),
                      child: FaIcon(FontAwesomeIcons.circleQuestion, color: Color(0xFF8E8E93), size: 20),
                    ),
                  ),
                  const SizedBox(width: 16),
                  const Expanded(
                    child: Text(
                      'Charging Issues',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ),
                  const Icon(
                    Icons.chevron_right,
                    color: Color(0xFF3C3C43),
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          // Disconnect
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          GestureDetector(
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
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
              child: Row(
                children: [
                  const SizedBox(
                    width: 24,
                    height: 24,
                    child: Padding(
                      padding: EdgeInsets.only(left: 2, top: 1),
                      child: FaIcon(FontAwesomeIcons.linkSlash, color: Colors.redAccent, size: 20),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Text(
                    provider.connectedDevice == null ? 'Unpair Device' : 'Disconnect Device',
                    style: const TextStyle(
                      color: Colors.redAccent,
                      fontSize: 17,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),
          ),
          // Unpair Device - only for Limitless devices
          if (provider.connectedDevice?.type == DeviceType.limitless) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            GestureDetector(
              onTap: () async {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () => Navigator.of(context).pop(),
                    () async {
                      Navigator.of(context).pop();
                      await SharedPreferencesUtil()
                          .btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0));
                      SharedPreferencesUtil().deviceName = '';
                      if (provider.connectedDevice != null) {
                        await _bleUnpairDevice(provider.connectedDevice!);
                      }
                      if (context.mounted) {
                        context.read<DeviceProvider>().setIsConnected(false);
                        context.read<DeviceProvider>().setConnectedDevice(null);
                        context.read<DeviceProvider>().updateConnectingStatus(false);
                        Navigator.of(context).pop();
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                                'Device unpaired. Go to Settings > Bluetooth and forget the device to complete unpairing.'),
                            duration: Duration(seconds: 5),
                          ),
                        );
                      }
                    },
                    'Unpair Device',
                    'This will unpair the device so it can be connected to another phone. You will need to go to Settings > Bluetooth and forget the device to complete the process.',
                    okButtonText: 'Unpair',
                  ),
                );
              },
              child: const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16, vertical: 18),
                child: Row(
                  children: [
                    SizedBox(
                      width: 24,
                      height: 24,
                      child: Padding(
                        padding: EdgeInsets.only(left: 2, top: 1),
                        child: FaIcon(FontAwesomeIcons.ban, color: Colors.orange, size: 20),
                      ),
                    ),
                    SizedBox(width: 16),
                    Text(
                      'Unpair and Forget Device',
                      style: TextStyle(
                        color: Colors.orange,
                        fontSize: 17,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildDeviceInfoSection(DeviceProvider provider) {
    final deviceName = provider.pairedDevice?.name ?? 'Unknown Device';
    final modelNumber = provider.pairedDevice?.modelNumber ?? 'Unknown';
    final manufacturer = provider.pairedDevice?.manufacturerName ?? 'Unknown';
    final firmware = provider.pairedDevice?.firmwareRevision ?? 'Unknown';
    final deviceId = provider.pairedDevice?.id ?? 'Unknown';
    final serialNumber = provider.pairedDevice?.id.replaceAll(':', '').replaceAll('-', '').toUpperCase() ?? 'Unknown';

    String truncateValue(String value) {
      if (value.length > 12) {
        return '${value.substring(0, 5)}•••${value.substring(value.length - 4)}';
      }
      return value;
    }

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.microchip,
            title: 'Product Name',
            chipValue: deviceName,
            copyValue: deviceName,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.hashtag,
            title: 'Model Number',
            chipValue: modelNumber,
            copyValue: modelNumber,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.industry,
            title: 'Manufacturer',
            chipValue: manufacturer,
            copyValue: manufacturer,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.code,
            title: 'Firmware',
            chipValue: firmware,
            copyValue: firmware,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.fingerprint,
            title: 'Device ID',
            chipValue: truncateValue(deviceId),
            copyValue: deviceId,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.barcode,
            title: 'Serial Number',
            chipValue: truncateValue(serialNumber),
            copyValue: serialNumber,
            showChevron: false,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<DeviceProvider, CaptureProvider>(builder: (context, provider, captureProvider, child) {
      return Scaffold(
        backgroundColor: const Color(0xFF0D0D0D),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0D0D0D),
          elevation: 0,
          leading: IconButton(
            icon: const FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 20),
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
                      color: provider.connectedDevice != null
                          ? Colors.green.withValues(alpha: 0.2)
                          : Colors.grey.withValues(alpha: 0.2),
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
                deviceType: provider.connectedDevice?.type,
                modelNumber: provider.connectedDevice?.modelNumber,
                isConnected: provider.connectedDevice != null,
                deviceName: provider.connectedDevice?.name ?? provider.pairedDevice?.name,
                animatedBackground: provider.connectedDevice != null,
              ),

              const SizedBox(height: 24),

              // Battery Level Section
              if (provider.connectedDevice != null) ...[
                _buildBatterySection(provider),
                const SizedBox(height: 16),
              ],

              // Actions Section
              _buildActionsSection(provider),
              const SizedBox(height: 16),

              // Device Info Section
              _buildDeviceInfoSection(provider),

              // Streaming Metrics Section - Bottom
              if (provider.connectedDevice != null && captureProvider.havingRecordingDevice) ...[
                const SizedBox(height: 32),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const FaIcon(
                      FontAwesomeIcons.bluetooth,
                      color: Colors.grey,
                      size: 14,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${captureProvider.bleReceiveRateKbps.toStringAsFixed(1)} kbps',
                      style: const TextStyle(
                        color: Colors.grey,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(width: 24),
                    const FaIcon(
                      FontAwesomeIcons.signal,
                      color: Colors.grey,
                      size: 14,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${captureProvider.wsSendRateKbps.toStringAsFixed(1)} kbps',
                      style: const TextStyle(
                        color: Colors.grey,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ],

              const SizedBox(height: 48),
            ],
          ),
        ),
      );
    });
  }
}
