import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/device_widget.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'firmware_update.dart';
import 'omiglass_ota_update.dart';

class ConnectedDevice extends StatefulWidget {
  const ConnectedDevice({super.key});

  @override
  State<ConnectedDevice> createState() => _ConnectedDeviceState();
}

class _ConnectedDeviceState extends State<ConnectedDevice> {
  CaptureProvider? _captureProvider;

  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  Future _bleUnpairDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    await connection.unpair();
    return await connection.disconnect();
  }

  @override
  void initState() {
    super.initState();
    // Register as a metrics listener immediately to avoid race condition
    // where widget unmounts before async getDeviceInfo completes
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _captureProvider = context.read<CaptureProvider>();
      _captureProvider!.addMetricsListener();
      context.read<DeviceProvider>().getDeviceInfo();
    });
  }

  @override
  void dispose() {
    _captureProvider?.removeMetricsListener();
    super.dispose();
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
      SnackBar(content: Text(context.l10n.copiedToClipboard(title))),
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
            Expanded(
              child: Text(
                context.l10n.batteryLevel,
                style: const TextStyle(
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
            title: context.l10n.productUpdate,
            chipValue: provider.connectedDevice == null
                ? context.l10n.offline
                : provider.havingNewFirmware
                    ? context.l10n.available
                    : null,
            onTap: provider.connectedDevice != null
                ? () {
                    // Route to OmiGlass OTA page for openglass devices
                    final deviceName = provider.connectedDevice?.name?.toLowerCase() ?? '';
                    final isOpenGlass = provider.connectedDevice?.type == DeviceType.openglass ||
                        deviceName.contains('openglass') ||
                        deviceName.contains('omiglass') ||
                        deviceName.contains('glass');
                    debugPrint('ProductUpdate: connectedDevice type: ${provider.connectedDevice?.type}');
                    debugPrint('ProductUpdate: connectedDevice name: "${provider.connectedDevice?.name}"');
                    debugPrint('ProductUpdate: deviceName lowercase: "$deviceName"');
                    debugPrint('ProductUpdate: isOpenGlass: $isOpenGlass');
                    if (isOpenGlass) {
                      debugPrint('ProductUpdate: Routing to OmiGlassOtaUpdate');
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => OmiGlassOtaUpdate(
                            device: provider.pairedDevice,
                            latestFirmwareDetails: provider.latestOmiGlassFirmwareDetails,
                          ),
                        ),
                      );
                    } else {
                      debugPrint('ProductUpdate: Routing to FirmwareUpdate');
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (context) => FirmwareUpdate(device: provider.pairedDevice),
                        ),
                      );
                    }
                  }
                : null,
            showChevron: provider.connectedDevice != null,
          ),
          // SD Card Sync
          if (provider.isDeviceStorageSupport) ...[
            const Divider(height: 1, color: Color(0xFF3C3C43)),
            _buildProfileStyleItem(
              icon: FontAwesomeIcons.sdCard,
              title: context.l10n.sdCardSync,
              chipValue: pendingSeconds > 0 ? secondsToCompactDuration(pendingSeconds, context) : null,
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
                  Expanded(
                    child: Text(
                      context.l10n.chargingIssues,
                      style: const TextStyle(
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
                    provider.connectedDevice == null ? context.l10n.unpairDevice : context.l10n.disconnectDevice,
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
                          SnackBar(
                            content: Text(context.l10n.deviceUnpairedMessage),
                            duration: const Duration(seconds: 5),
                          ),
                        );
                      }
                    },
                    context.l10n.unpairDeviceDialogTitle,
                    context.l10n.unpairDeviceDialogMessage,
                    okButtonText: context.l10n.unpair,
                  ),
                );
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
                        child: FaIcon(FontAwesomeIcons.ban, color: Colors.orange, size: 20),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Text(
                      context.l10n.unpairAndForgetDevice,
                      style: const TextStyle(
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
    final deviceName = provider.pairedDevice?.name ?? context.l10n.unknownDevice;
    final modelNumber = provider.pairedDevice?.modelNumber ?? context.l10n.unknown;
    final manufacturer = provider.pairedDevice?.manufacturerName ?? context.l10n.unknown;
    final firmware = provider.pairedDevice?.firmwareRevision ?? context.l10n.unknown;
    final deviceId = provider.pairedDevice?.id ?? context.l10n.unknown;
    final serialNumber = provider.pairedDevice?.serialNumber ??
        provider.pairedDevice?.id.replaceAll(':', '').replaceAll('-', '').toUpperCase() ??
        context.l10n.unknown;

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
            title: context.l10n.productName,
            chipValue: deviceName,
            copyValue: deviceName,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.hashtag,
            title: context.l10n.modelNumber,
            chipValue: modelNumber,
            copyValue: modelNumber,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.industry,
            title: context.l10n.manufacturer,
            chipValue: manufacturer,
            copyValue: manufacturer,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.code,
            title: context.l10n.firmware,
            chipValue: firmware,
            copyValue: firmware,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.fingerprint,
            title: context.l10n.deviceId,
            chipValue: truncateValue(deviceId),
            copyValue: deviceId,
            showChevron: false,
          ),
          const Divider(height: 1, color: Color(0xFF3C3C43)),
          _buildProfileStyleItem(
            icon: FontAwesomeIcons.barcode,
            title: context.l10n.serialNumber,
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
                    provider.pairedDevice?.name ?? context.l10n.unknownDevice,
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
                          provider.connectedDevice != null ? context.l10n.connected : context.l10n.offline,
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
              if (provider.connectedDevice != null && provider.batteryLevel > 0) ...[
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
