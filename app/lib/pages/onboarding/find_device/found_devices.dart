import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:gradient_borders/gradient_borders.dart';

class FoundDevices extends StatefulWidget {
  final List<BTDeviceStruct> deviceList;
  final VoidCallback goNext;

  const FoundDevices({
    super.key,
    required this.deviceList,
    required this.goNext,
  });

  @override
  _FoundDevicesState createState() => _FoundDevicesState();
}

class _FoundDevicesState extends State<FoundDevices> {
  bool _isClicked = false;
  bool _isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  String deviceId = '';
  String? _connectingToDeviceId;

  Timer? connectionStateTimer;

  // TODO: improve this and find_device page.
  // TODO: include speech profile, once it's well tested, in a few days, rn current version works

  Future<void> setBatteryPercentage(BTDeviceStruct btDevice) async {
    try {
      var battery = await retrieveBatteryLevel(btDevice.id);
      setState(() {
        batteryPercentage = battery;
        _isConnected = true;
        _isClicked = false; // Allow clicks again after finishing the operation
        _connectingToDeviceId = null; // Reset the connecting device
      });
      await Future.delayed(const Duration(seconds: 2));
      SharedPreferencesUtil().btDeviceStruct = btDevice;
      SharedPreferencesUtil().deviceName = btDevice.name;
      widget.goNext();
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
    deviceId = device.id;
    deviceName = device.name;
    getAudioCodec(deviceId).then((codec) => SharedPreferencesUtil().deviceCodec = codec);
    setBatteryPercentage(device);
  }

  @override
  void initState() {
    _initiateConnectionListener();
    super.initState();
  }

  _initiateConnectionListener() async {
    connectionStateTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      var connectedDevice = await getConnectedDevice();
      if (connectedDevice != null) {
        if (mounted) {
          connectionStateTimer?.cancel();
          var battery = await retrieveBatteryLevel(connectedDevice.id);
          setState(() {
            deviceName = connectedDevice.name;
            deviceId = connectedDevice.id;
            batteryPercentage = battery;
            _isConnected = true;
            _isClicked = false;
            _connectingToDeviceId = null;
          });
          await Future.delayed(const Duration(seconds: 2));
          widget.goNext();
        }
      }
    });
  }

  @override
  void dispose() {
    connectionStateTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        !_isConnected
            ? Text(
                widget.deviceList.isEmpty
                    ? 'Searching for devices...'
                    : '${widget.deviceList.length} ${widget.deviceList.length == 1 ? "DEVICE" : "DEVICES"} FOUND NEARBY',
                style: const TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 14,
                  color: Color(0x66FFFFFF),
                ),
              )
            : const Text(
                'PAIRING SUCCESSFUL',
                style: TextStyle(
                  fontWeight: FontWeight.w400,
                  fontSize: 12,
                  color: Color(0x66FFFFFF),
                ),
              ),
        if (widget.deviceList.isNotEmpty) const SizedBox(height: 16),
        if (!_isConnected) ..._devicesList(),
        if (_isConnected)
          Text(
            '$deviceName (${BTDeviceStruct.shortId(deviceId)})',
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
    );
  }

  _devicesList() {
    return (widget.deviceList.mapIndexed((index, device) {
      bool isConnecting = _connectingToDeviceId == device.id;

      return GestureDetector(
        onTap: !_isClicked ? () => handleTap(device) : null,
        child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
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
            ),
            child: Row(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(16.0),
                    child: Stack(
                      children: [
                        Align(
                          alignment: Alignment.center,
                          child: Text(
                            '${device.name} (${device.getShortId()})',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontWeight: FontWeight.w500,
                              fontSize: 18,
                              color: Color(0xCCFFFFFF),
                            ),
                          ),
                        ),
                        Align(
                          alignment: Alignment.centerRight,
                          child: isConnecting
                              ? const SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  ),
                                )
                              : const SizedBox.shrink(), // Show loading indicator if connecting
                        )
                      ],
                    ),
                  ),
                ),
              ],
            )),
      );
    }).toList());
  }
}
