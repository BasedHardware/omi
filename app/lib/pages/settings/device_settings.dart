import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/firmware_update.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:provider/provider.dart';

class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key});

  @override
  State<DeviceSettings> createState() => _DeviceSettingsState();
}

class _DeviceSettingsState extends State<DeviceSettings> {
  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BTDeviceStruct btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DeviceProvider>().getDeviceInfo();
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
        body: Padding(
          padding: const EdgeInsets.all(4.0),
          child: ListView(
            children: [
              Stack(
                children: [
                  Column(
                    children: deviceSettingsWidgets(provider.deviceInfo, provider.connectedDevice, context),
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
              GestureDetector(
                onTap: () async {
                  await Intercom.instance.displayArticle('9907475-how-to-charge-the-device');
                },
                child: const ListTile(
                  title: Text('Issues charging the device?'),
                  subtitle: Text('Tap to see the guide'),
                ),
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
                      await SharedPreferencesUtil().btDeviceStructSet(BTDeviceStruct(id: '', name: ''));
                      SharedPreferencesUtil().deviceName = '';
                      if (provider.connectedDevice != null) {
                        await _bleDisconnectDevice(provider.connectedDevice!);
                      }
                      provider.setIsConnected(false);
                      provider.setConnectedDevice(null);
                      provider.updateConnectingStatus(false);
                      context.read<OnboardingProvider>().stopFindDeviceTimer();
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

List<Widget> deviceSettingsWidgets(DeviceInfo? deviceInfo, BTDeviceStruct? device, BuildContext context) {
  return [
    ListTile(
      title: const Text('Device Name'),
      subtitle: Text(device?.name ?? 'Friend'),
    ),
    ListTile(
      title: const Text('Device ID'),
      subtitle: Text(device?.id ?? '12AB34CD:56EF78GH'),
    ),
    GestureDetector(
      onTap: () {
        routeToPage(context, FirmwareUpdate(deviceInfo: deviceInfo!, device: device));
      },
      child: ListTile(
        title: const Text('Update Latest Version'),
        subtitle: Text('Current: ${deviceInfo?.firmwareRevision ?? '1.0.2'}'),
        trailing: const Icon(
          Icons.arrow_forward_ios,
          size: 16,
        ),
      ),
    ),
    ListTile(
      title: const Text('Hardware Revision'),
      subtitle: Text(deviceInfo?.hardwareRevision ?? 'XIAO'),
    ),
    ListTile(
      title: const Text('Model Number'),
      subtitle: Text(deviceInfo?.modelNumber ?? 'Friend'),
    ),
    ListTile(
      title: const Text('Manufacturer Name'),
      subtitle: Text(deviceInfo?.manufacturerName ?? 'Based Hardware'),
    ),
  ];
}
