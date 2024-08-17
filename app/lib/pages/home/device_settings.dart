import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/firmware_update.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:gradient_borders/gradient_borders.dart';

import 'device.dart';
import 'support.dart';

class DeviceSettings extends StatelessWidget {
  final DeviceInfo? deviceInfo;
  final BTDeviceStruct? device;
  final bool isDeviceConnected;
  const DeviceSettings({super.key, this.deviceInfo, this.device, this.isDeviceConnected = false});

  @override
  Widget build(BuildContext context) {
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
                  children: deviceSettingsWidgets(deviceInfo, device, context),
                ),
                if (!isDeviceConnected)
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
                              'Connect your device to access these settings',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          )),
                    ),
                  ),
              ],
            ),
            GestureDetector(
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const SupportPage(),
                  ),
                );
              },
              child: const ListTile(
                title: Text('Guides & Support'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: isDeviceConnected
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
                  onPressed: () {
                    if (device != null) bleDisconnectDevice(device!);
                    SharedPreferencesUtil().btDeviceStruct = BTDeviceStruct(id: '', name: '');
                    SharedPreferencesUtil().deviceName = '';
                    Navigator.of(context).pop();
                    Navigator.of(context).pop();
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text('Your Friend is ${device == null ? "unpaired" : "disconnected"}  😔'),
                    ));
                    MixpanelManager().disconnectFriendClicked();
                  },
                  child: Text(
                    device == null ? "Unpair" : "Disconnect",
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              ),
            )
          : const SizedBox(),
    );
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
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => FirmwareUpdate(
              deviceInfo: deviceInfo!,
              device: device,
            ),
          ),
        );
      },
      child: ListTile(
        title: const Text('Firmware Update'),
        subtitle: Text(deviceInfo?.firmwareRevision ?? '1.0.2'),
        trailing: const Icon(Icons.arrow_forward_ios),
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
