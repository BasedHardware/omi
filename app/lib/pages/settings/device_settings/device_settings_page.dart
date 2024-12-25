import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/pages/home/firmware_update.dart';
import 'package:friend_private/pages/conversations/sync_page.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/pages/settings/widgets.dart';

import 'widgets/device_info_card.dart';

class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key});

  @override
  State<DeviceSettings> createState() => _DeviceSettingsState();
}

class _DeviceSettingsState extends State<DeviceSettings> {
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

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Device Settings'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        body: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 16),
              Stack(
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      DeviceInfoCard(device: provider.pairedDevice),
                      const SizedBox(height: 24),
                      // Actions Section
                      Padding(
                        padding: const EdgeInsets.only(left: 4, bottom: 12),
                        child: Text(
                          'ACTIONS',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                      CustomListTile(
                        title: 'Update Version',
                        onTap: () => routeToPage(context, FirmwareUpdate(device: provider.pairedDevice)),
                        icon: Icons.system_update,
                        subtitle: 'Current: ${provider.pairedDevice?.firmwareRevision ?? '1.0.2'}',
                        showChevron: true,
                      ),
                      const SizedBox(height: 8),
                      CustomListTile(
                        title: 'SD Card Sync',
                        onTap: () {
                          if (!provider.isDeviceV2Connected) {
                            showDialog(
                              context: context,
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.of(context).pop(),
                                () => {},
                                'V2 undetected',
                                'We see that you either have a V1 device or your device is not connected. SD Card functionality is available only for V2 devices.',
                                singleButton: true,
                              ),
                            );
                          } else {
                            routeToPage(context, const SyncPage());
                          }
                        },
                        icon: Icons.sd_card,
                        subtitle: 'Import audio files',
                        showChevron: true,
                      ),
                      const SizedBox(height: 24),
                      // Support Section
                      Padding(
                        padding: const EdgeInsets.only(left: 4, bottom: 12),
                        child: Text(
                          'SUPPORT',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                      CustomListTile(
                        title: 'Issues charging the device?',
                        onTap: () async {
                          await IntercomManager().displayChargingArticle(provider.pairedDevice?.name ?? 'DevKit1');
                        },
                        icon: Icons.help_outline,
                        subtitle: 'Tap to see the guide',
                        showChevron: true,
                      ),
                    ],
                  ),
                  if (!provider.isConnected)
                    ClipRRect(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(
                          sigmaX: 3.0,
                          sigmaY: 3.0,
                        ),
                        child: Container(
                          height: 410,
                          width: double.infinity,
                          margin: const EdgeInsets.only(top: 10),
                          decoration: BoxDecoration(
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.1),
                                spreadRadius: 5,
                                blurRadius: 7,
                                offset: const Offset(0, 3),
                              ),
                            ],
                          ),
                          child: const Center(
                            child: Text(
                              'Connect your device to\naccess these settings',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                height: 1.3,
                                fontWeight: FontWeight.w500,
                              ),
                              textAlign: TextAlign.center,
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
        bottomNavigationBar: provider.isConnected
            ? Padding(
                padding: const EdgeInsets.only(bottom: 70, left: 30, right: 30),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
                  decoration: BoxDecoration(
                    border: const GradientBoxBorder(
                      gradient: LinearGradient(colors: [
                        Color.fromARGB(127, 208, 208, 208),
                        Color.fromARGB(127, 188, 99, 121),
                        Color.fromARGB(127, 86, 101, 182),
                        Color.fromARGB(127, 126, 190, 236)
                      ]),
                      width: 2,
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: TextButton(
                    onPressed: () async {
                      await SharedPreferencesUtil()
                          .btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.friend, rssi: 0));
                      SharedPreferencesUtil().deviceName = '';
                      if (provider.connectedDevice != null) {
                        await _bleDisconnectDevice(provider.connectedDevice!);
                      }
                      provider.setIsConnected(false);
                      provider.setConnectedDevice(null);
                      provider.updateConnectingStatus(false);
                      context.read<OnboardingProvider>().stopScanDevices();
                      Navigator.of(context).pop();
                      Navigator.of(context).pop();
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(
                            'Your Friend is ${provider.connectedDevice == null ? "unpaired" : "disconnected"}  😔'),
                      ));
                      MixpanelManager().disconnectFriendClicked();
                    },
                    child: Text(
                      provider.connectedDevice == null ? "Unpair" : "Disconnect",
                      style: const TextStyle(color: Colors.white, fontSize: 16),
                    ),
                  ),
                ),
              )
            : const SizedBox(),
      );
    });
  }
}
