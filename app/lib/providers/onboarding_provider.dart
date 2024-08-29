import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/find.dart';

class OnboardingProvider extends BaseProvider with MessageNotifierMixin {
  DeviceProvider? deviceProvider;
  bool isClicked = false;
  bool isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  String deviceId = '';
  String? connectingToDeviceId;
  Timer? connectionStateTimer;
  List<BTDeviceStruct> deviceList = [];
  late Timer _didNotMakeItTimer;
  late Timer _findDevicesTimer;
  bool enableInstructions = false;
  Map<String, BTDeviceStruct> foundDevicesMap = {};

  void stopFindDeviceTimer() {
    if (_findDevicesTimer != null && _findDevicesTimer.isActive) {
      _findDevicesTimer.cancel();
    }
    if (connectionStateTimer?.isActive ?? false) {
      connectionStateTimer?.cancel();
    }
    notifyListeners();
  }

  void setDeviceProvider(DeviceProvider provider) {
    deviceProvider = provider;
  }

  // TODO: improve this and find_device page.
  // TODO: include speech profile, once it's well tested, in a few days, rn current version works

  // Method to handle taps on devices
  Future<void> handleTap({
    required BTDeviceStruct device,
  }) async {
    if (isClicked) return; // if any item is clicked, don't do anything

    isClicked = true; // Prevent further clicks
    connectingToDeviceId = device.id; // Mark this device as being connected to
    notifyListeners();
    await bleConnectDevice(device.id);
    deviceId = device.id;
    SharedPreferencesUtil().btDeviceStruct = device;
    deviceName = device.name;
    var cDevice = await getConnectedDevice();
    if (cDevice != null) {
      deviceProvider!.setConnectedDevice(cDevice);
      SharedPreferencesUtil().btDeviceStruct = cDevice;
      SharedPreferencesUtil().deviceName = cDevice.name;
      deviceProvider!.setIsConnected(true);
    }
    //TODO: should'nt update codec here, becaause then the prev connection codec and the current codec will
    // become same and the app won't transcribe at all because inherently there's a mismatch in the
    //codec for websocket and the codec for the device
    // await getAudioCodec(deviceId).then((codec) => SharedPreferencesUtil().deviceCodec = codec);
    await deviceProvider?.scanAndConnectToDevice();
    var connectedDevice = deviceProvider!.connectedDevice;
    batteryPercentage = deviceProvider!.batteryLevel;
    isConnected = true;
    isClicked = false; // Allow clicks again after finishing the operation
    connectingToDeviceId = null; // Reset the connecting device
    notifyListeners();
    stopFindDeviceTimer();
    await Future.delayed(const Duration(seconds: 2));
    SharedPreferencesUtil().btDeviceStruct = connectedDevice!;
    SharedPreferencesUtil().deviceName = connectedDevice.name;
    foundDevicesMap.clear();
    deviceList.clear();
    notifyInfo('DEVICE_CONNECTED');
    notifyListeners();
  }

  void deviceAlreadyUnpaired() {
    batteryPercentage = -1;
    isConnected = false;
    deviceName = '';
    deviceId = '';
    notifyListeners();
  }

  Future<void> scanDevices({
    required VoidCallback onShowDialog,
  }) async {
    if (SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
      // it means the device has been unpaired
      deviceAlreadyUnpaired();
    }
    // check if bluetooth is enabled on Android
    if (Platform.isAndroid) {
      if (FlutterBluePlus.adapterStateNow != BluetoothAdapterState.on) {
        try {
          await FlutterBluePlus.turnOn();
        } catch (e) {
          if (e is FlutterBluePlusException) {
            if (e.code == 11) {
              onShowDialog();
            }
          }
        }
      }
    }
    _didNotMakeItTimer = Timer(const Duration(seconds: 10), () {
      enableInstructions = true;
      notifyListeners();
    });

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
        deviceList = orderedDevices;
        notifyListeners();
        _didNotMakeItTimer.cancel();
      }
    });
  }

  @override
  void dispose() {
    //TODO: This does not get called when the page is popped
    _findDevicesTimer.cancel();
    _didNotMakeItTimer.cancel();
    connectionStateTimer?.cancel();
    super.dispose();
  }
}
