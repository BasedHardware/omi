import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/pages/speaker_id/page.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/gradient_borders.dart';

class FoundDevices extends StatefulWidget {
  final List<BTDeviceStruct?> deviceList;

  const FoundDevices({
    super.key,
    required this.deviceList,
  });

  @override
  _FoundDevicesState createState() => _FoundDevicesState();
}

class _FoundDevicesState extends State<FoundDevices> with TickerProviderStateMixin {
  bool _isClicked = false;
  bool _isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  String? _connectingToDeviceId;

  Future<void> setBatteryPercentage(BTDeviceStruct btDevice) async {
    try {
      var battery = await retrieveBatteryLevel(btDevice);
      setState(() {
        batteryPercentage = battery;
        _isConnected = true;
        _isClicked = false; // Allow clicks again after finishing the operation
        _connectingToDeviceId = null; // Reset the connecting device
      });
      await Future.delayed(const Duration(seconds: 2));
      SharedPreferencesUtil().onboardingCompleted = true;
      SharedPreferencesUtil().deviceId = btDevice.id;
      MixpanelManager().onboardingCompleted();
      debugPrint("Onboarding completed");
      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const SpeakerIdPage(onbording: true)));
      // Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
    } catch (e) {
      print("Error fetching battery level: $e");
      setState(() {
        _isClicked = false; // Allow clicks again if an error occurs
        _connectingToDeviceId = null; // Reset the connecting device
      });
    }
  }

  // Method to handle taps on devices
  Future<void> handleTap(BTDeviceStruct device) async {
    if (_isClicked) return; // if any item is clicked, don't do anything
    setState(() {
      _isClicked = true; // Prevent further clicks
      _connectingToDeviceId = device.id; // Mark this device as being connected to
    });
    await bleConnectDevice(device.id);
    deviceName = device.id;
    setBatteryPercentage(device);
  }

  @override
  Widget build(BuildContext context) {
    var screenSize = MediaQuery.of(context).size;
    return Expanded(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const DeviceAnimationWidget(),
          !_isConnected
              ? Container(
                  margin: const EdgeInsets.fromLTRB(0, 0, 4, 12),
                  child: Text(
                    widget.deviceList.isEmpty
                        ? 'Searching for devices...'
                        : '${widget.deviceList.length} ${widget.deviceList.length == 1 ? "DEVICE" : "DEVICES"} FOUND NEARBY',
                    style: const TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 12,
                      color: Color(0x66FFFFFF),
                    ),
                  ),
                )
              : Container(
                  margin: const EdgeInsets.fromLTRB(0, 0, 4, 12),
                  child: const Text(
                    'PAIRING SUCCESSFUL',
                    style: TextStyle(
                      fontWeight: FontWeight.w400,
                      fontSize: 12,
                      color: Color(0x66FFFFFF),
                    ),
                  ),
                ),
          !_isConnected
              ? Expanded(
                  // Create a scrollable list of devices
                  child: ListView.builder(
                    shrinkWrap: true,
                    itemCount: widget.deviceList.length,
                    itemBuilder: (context, index) {
                      final device = widget.deviceList[index];
                      if (device == null) return Container(); // If device is null, return an empty container

                      bool isConnecting =
                          _connectingToDeviceId == device.id; // Check if it's the device being connected to

                      return Container(
                        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                        padding: EdgeInsets.symmetric(horizontal: screenSize.width * 0, vertical: 0),
                        decoration: BoxDecoration(
                          border: const GradientBoxBorder(
                            gradient: LinearGradient(colors: [
                              Color.fromARGB(127, 208, 208, 208),
                              Color.fromARGB(127, 188, 99, 121),
                              Color.fromARGB(127, 86, 101, 182),
                              Color.fromARGB(127, 126, 190, 236)
                            ]),
                            width: 1,
                          ),
                          borderRadius: BorderRadius.circular(12),
                          color: const Color.fromARGB(0, 0, 0, 0),
                        ),
                        child: ListTile(
                          title: Text(
                            device.id.split('-').last.substring(0, 6),
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 18,
                              color: Color(0xCCFFFFFF),
                            ),
                          ),
                          trailing: isConnecting
                              ? Container(
                                  padding: const EdgeInsets.all(8.0),
                                  height: 24,
                                  width: 24,
                                  child: const CircularProgressIndicator(
                                    strokeWidth: 3.0,
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                )
                              : null, // Show loading indicator if connecting
                          onTap: !_isClicked ? () => handleTap(device) : null,
                        ),
                      );
                    },
                  ),
                )
              : Text(
                  deviceName.split('-').last.substring(0, 6),
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 18,
                    color: Color(0xCCFFFFFF),
                  ),
                ),
          if (_isConnected)
            Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Text(
                  '🔋 ${batteryPercentage.toString()}%',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 18,
                    color: batteryPercentage <= 25
                        ? Colors.red
                        : batteryPercentage > 25 && batteryPercentage <= 50
                            ? Colors.orange
                            : Colors.green,
                  ),
                ))
        ],
      ),
    );
  }
}
