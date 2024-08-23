import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/find.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:url_launcher/url_launcher.dart';

import 'found_devices.dart';

class FindDevicesPage extends StatefulWidget {
  final VoidCallback goNext;
  final bool includeSkip;

  const FindDevicesPage({super.key, required this.goNext, this.includeSkip = true});

  @override
  _FindDevicesPageState createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage> {
  List<BTDeviceStruct> deviceList = [];
  late Timer _didNotMakeItTimer;
  late Timer _findDevicesTimer;
  bool enableInstructions = false;

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _scanDevices();
    });
  }

  @override
  void dispose() {
    _findDevicesTimer.cancel();
    _didNotMakeItTimer.cancel();
    super.dispose();
  }

  Future<void> _scanDevices() async {
    // check if bluetooth is enabled on Android
    if (Platform.isAndroid) {
      if (FlutterBluePlus.adapterStateNow != BluetoothAdapterState.on) {
        try {
          await FlutterBluePlus.turnOn();
        } catch (e) {
          if (e is FlutterBluePlusException) {
            if (e.code == 11) {
              if (mounted) {
                showDialog(
                  context: context,
                  builder: (c) => getDialog(
                    context,
                    () {
                      Navigator.of(context).pop();
                    },
                    () {},
                    'Enable Bluetooth',
                    'Friend needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.',
                    singleButton: true,
                  ),
                );
              }
            }
          }
        }
      }
    }

    _didNotMakeItTimer = Timer(const Duration(seconds: 10), () => setState(() => enableInstructions = true));
    // Update foundDevicesMap with new devices and remove the ones not found anymore
    Map<String, BTDeviceStruct> foundDevicesMap = {};

    _findDevicesTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      List<BTDeviceStruct> foundDevices = await bleFindDevices();

      // Update foundDevicesMap with new devices and remove the ones not found anymore
      Map<String, BTDeviceStruct> updatedDevicesMap = {};
      for (final device in foundDevices) {
        // If it's a new device, add it to the map. If it already exists, this will just update the entry.
        updatedDevicesMap[device.id] = device;
      }
      // Remove devices that are no longer found
      foundDevicesMap.keys.where((id) => !updatedDevicesMap.containsKey(id)).toList().forEach(foundDevicesMap.remove);

      // Merge the new devices into the current map to maintain order
      foundDevicesMap.addAll(updatedDevicesMap);

      // Convert the values of the map back to a list
      List<BTDeviceStruct> orderedDevices = foundDevicesMap.values.toList();

      if (orderedDevices.isNotEmpty) {
        if (mounted) {
          setState(() {
            deviceList = orderedDevices;
          });
        }

        _didNotMakeItTimer.cancel();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        FoundDevices(deviceList: deviceList, goNext: widget.goNext),
        if (deviceList.isEmpty && enableInstructions) const SizedBox(height: 48),
        if (deviceList.isEmpty && enableInstructions)
          ElevatedButton(
            onPressed: () => launchUrl(Uri.parse('mailto:team@basedhardware.com')),
            child: Container(
              width: double.infinity,
              height: 45,
              alignment: Alignment.center,
              child: const Text(
                'Contact Support?',
                style: TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 16,
                  color: Colors.white,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
        if (widget.includeSkip && deviceList.isEmpty)
          ElevatedButton(
            onPressed: () {
              widget.goNext();
              MixpanelManager().useWithoutDeviceOnboardingFindDevices();
            },
            child: Container(
              width: double.infinity,
              height: 45,
              alignment: Alignment.center,
              child: const Text(
                'Connect Later',
                style: TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 16,
                  color: Colors.white,
                  // decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
