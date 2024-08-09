import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/firmware_update.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:gradient_borders/gradient_borders.dart';

import 'device.dart';

class DeviceSettings extends StatelessWidget {
  final DeviceInfo deviceInfo;
  final BTDeviceStruct? device;
  const DeviceSettings({super.key, required this.deviceInfo, this.device});

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
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              title: const Text('Device Name'),
              subtitle: Text(device?.name ?? ''),
            ),
            ListTile(
              title: const Text('Device ID'),
              subtitle: Text(device?.id ?? ''),
            ),
            GestureDetector(
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => FirmwareUpdate(
                      deviceInfo: deviceInfo,
                      device: device,
                    ),
                  ),
                );
              },
              child: ListTile(
                title: const Text('Firmware Update'),
                subtitle: Text(deviceInfo.firmwareRevision),
                trailing: const Icon(Icons.arrow_forward_ios),
              ),
            ),
            ListTile(
              title: const Text('Hardware Revision'),
              subtitle: Text(deviceInfo.hardwareRevision),
            ),
            ListTile(
              title: const Text('Model Number'),
              subtitle: Text(deviceInfo.modelNumber),
            ),
            ListTile(
              title: const Text('Manufacturer Name'),
              subtitle: Text(deviceInfo.manufacturerName),
            ),
            GestureDetector(
              onTap: () {},
              child: const ListTile(
                title: Text('Guides & Support'),
                trailing: Icon(Icons.arrow_forward_ios),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: Padding(
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
              SharedPreferencesUtil().deviceId = '';
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
      ),
    );
  }
}
