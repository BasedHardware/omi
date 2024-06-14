import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:url_launcher/url_launcher.dart';

import 'found_devices.dart';

class FindDevicesPage extends StatefulWidget {
  const FindDevicesPage({super.key});

  @override
  _FindDevicesPageState createState() => _FindDevicesPageState();
}

class _FindDevicesPageState extends State<FindDevicesPage> with SingleTickerProviderStateMixin {
  List<BTDeviceStruct?> deviceList = [];
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
    // TODO: validate bluetooth turned on
    _didNotMakeItTimer = Timer(const Duration(seconds: 10), () {
      setState(() {
        enableInstructions = true;
      });
    });
    // Update foundDevicesMap with new devices and remove the ones not found anymore
    Map<String, BTDeviceStruct?> foundDevicesMap = {};

    _findDevicesTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      List<BTDeviceStruct?> foundDevices = await scanDevices();

      // Update foundDevicesMap with new devices and remove the ones not found anymore
      Map<String, BTDeviceStruct?> updatedDevicesMap = {};
      for (final device in foundDevices) {
        if (device != null) {
          // If it's a new device, add it to the map. If it already exists, this will just update the entry.
          updatedDevicesMap[device.id] = device;
        }
      }
      // Remove devices that are no longer found
      foundDevicesMap.keys.where((id) => !updatedDevicesMap.containsKey(id)).toList().forEach(foundDevicesMap.remove);

      // Merge the new devices into the current map to maintain order
      foundDevicesMap.addAll(updatedDevicesMap);

      // Convert the values of the map back to a list
      List<BTDeviceStruct?> orderedDevices = foundDevicesMap.values.toList();

      if (orderedDevices.isNotEmpty) {
        setState(() {
          deviceList = orderedDevices;
        });
        _didNotMakeItTimer.cancel();
      }
    });
  }

  void _launchURL() async {
    const url = 'https://discord.com/servers/based-hardware-1192313062041067520';
    if (!await launch(url)) throw 'Could not launch $url';
  }

  @override
  Widget build(BuildContext context) {
    var screenSize = MediaQuery.of(context).size;
    var size = MediaQuery.of(context).size; // obtain MediaQuery data
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: SafeArea(
        child: Container(
          height: size.height, // Make the container take up the full height
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 0), // Responsive padding
          child: Column(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              FoundDevices(deviceList: deviceList),
              deviceList.isEmpty
                  ? enableInstructions
                      ? Padding(
                          padding: EdgeInsets.only(
                            bottom: 20, // Padding from the bottom for the button
                            left: screenSize.width * 0.0, // Horizontal padding for button
                            right: screenSize.width * 0.0,
                          ),
                          child: Padding(
                            padding: EdgeInsets.only(
                              bottom: 10, // Padding from the bottom for the button
                              left: screenSize.width * 0.0, // Horizontal padding for button
                              right: screenSize.width * 0.0,
                            ),
                            child: Container(
                              decoration: BoxDecoration(
                                border: Border.all(color: const Color.fromARGB(255, 55, 55, 55), width: 2.0),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: ElevatedButton(
                                onPressed: () {
                                  _launchURL();
                                },
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.transparent,
                                  shadowColor: const Color.fromARGB(255, 17, 17, 17),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                ),
                                child: Container(
                                  width: double.infinity, // Button takes full width of the padding
                                  height: 45, // Fixed height for the button
                                  alignment: Alignment.center,
                                  child: Text(
                                    'Contact Support',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w400,
                                        fontSize: screenSize.width * 0.045,
                                        color: const Color.fromARGB(255, 55, 55, 55)),
                                  ),
                                ),
                              ),
                            ),
                          ))
                      : const SizedBox.shrink()
                  : const SizedBox.shrink()
            ],
          ),
        ),
      ),
    );
  }
}

class SearchingSection extends StatelessWidget {
  final bool enableInstructions;

  const SearchingSection({
    super.key,
    required this.enableInstructions,
  });

  @override
  Widget build(BuildContext context) {
    var screenSize = MediaQuery.of(context).size;
    return Expanded(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Padding(
            padding: EdgeInsets.only(bottom: 12, top: screenSize.height * 0.08),
            child: const Text(
              'SEARCHING FOR FRIEND...',
              style: TextStyle(
                color: Color.fromARGB(255, 255, 255, 255),
                fontSize: 17,
                fontWeight: FontWeight.normal,
              ),
            ),
          ),
          if (enableInstructions)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 10.0),
              child: Text(
                "Check if your device is charged by double tapping the top. A green light should be blinking on the side if it's charged.",
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Color.fromARGB(127, 255, 255, 255),
                  fontSize: 12,
                  fontWeight: FontWeight.normal,
                ),
              ),
            ),
          const Spacer(),
          Center(
            child: Image.asset(
              "assets/images/searching.png",
              width: MediaQuery.of(context).size.width * 0.9,
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }
}
