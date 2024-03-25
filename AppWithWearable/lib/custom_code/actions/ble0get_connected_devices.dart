// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

Future<List<BTDeviceStruct>> ble0getConnectedDevices() async {
  final connectedDevices = await FlutterBluePlus.connectedDevices;
  List<BTDeviceStruct> devices = [];

  for (int i = 0; i < connectedDevices.length; i++) {
    final deviceResult = connectedDevices[i];
    final deviceState = deviceResult.state;

    if (deviceState == BluetoothDeviceState.connected) {
      final deviceRssi = await deviceResult.readRssi();
      devices.add(BTDeviceStruct(
        name: deviceResult.name,
        id: deviceResult.id.toString(),
        rssi: deviceRssi,
      ));
    }
  }

  return devices;
}
