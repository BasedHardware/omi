import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/connected.dart';

class OnboardingProvider extends BaseProvider {
  bool isClicked = false;
  bool isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  String deviceId = '';
  String? connectingToDeviceId;

  Timer? connectionStateTimer;

  // TODO: improve this and find_device page.
  // TODO: include speech profile, once it's well tested, in a few days, rn current version works

  Future<void> setBatteryPercentage({
    required BTDeviceStruct btDevice,
    required VoidCallback goNext,
  }) async {
    try {
      var battery = await retrieveBatteryLevel(btDevice.id);

      batteryPercentage = battery;
      isConnected = true;
      isClicked = false; // Allow clicks again after finishing the operation
      connectingToDeviceId = null; // Reset the connecting device
      notifyListeners();
      await Future.delayed(const Duration(seconds: 2));
      SharedPreferencesUtil().btDeviceStruct = btDevice;
      SharedPreferencesUtil().deviceName = btDevice.name;
      goNext();
    } catch (e) {
      print("Error fetching battery level: $e");

      isClicked = false; // Allow clicks again if an error occurs
      connectingToDeviceId = null; // Reset the connecting device
      notifyListeners();
    }
  }

  // Method to handle taps on devices
  Future<void> handleTap({
    required BTDeviceStruct device,
    required VoidCallback goNext,
  }) async {
    if (isClicked) return; // if any item is clicked, don't do anything

    isClicked = true; // Prevent further clicks
    connectingToDeviceId = device.id; // Mark this device as being connected to
    notifyListeners();
    await bleConnectDevice(device.id);
    deviceId = device.id;
    deviceName = device.name;
    getAudioCodec(deviceId).then((codec) => SharedPreferencesUtil().deviceCodec = codec);
    setBatteryPercentage(
      btDevice: device,
      goNext: goNext,
    );
  }

  void initiateConnectionListener({
    required bool mounted,
    required VoidCallback goNext,
  }) async {
    connectionStateTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      var connectedDevice = await getConnectedDevice();
      if (connectedDevice != null) {
        if (mounted) {
          connectionStateTimer?.cancel();
          var battery = await retrieveBatteryLevel(connectedDevice.id);

          deviceName = connectedDevice.name;
          deviceId = connectedDevice.id;
          batteryPercentage = battery;
          isConnected = true;
          isClicked = false;
          connectingToDeviceId = null;
          notifyListeners();
          await Future.delayed(const Duration(seconds: 2));
          goNext();
        }
      }
    });
  }

  @override
  void dispose() {
    connectionStateTimer?.cancel();
    super.dispose();
  }
}
