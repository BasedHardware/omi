import 'package:flutter/material.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'page.dart' show FindDevicesWidget;

class FindDevicesModel extends FlutterFlowModel<FindDevicesWidget> {
  ///  Local state fields for this page.

  bool isFetchingDevices = false;
  bool isBluetoothEnabled = false;
  List<BTDeviceStruct> foundDevices = [];
  List<BTDeviceStruct> connectedDevices = [];
  bool isFetchingConnectedDevices = false;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();

  // Stores action output result for [Custom Action - ble0getConnectedDevices] action in findDevices widget.
  List<BTDeviceStruct>? fetchedConnectedDevices;

  // Stores action output result for [Custom Action - ble0findDevices] action in findDevices widget.
  List<BTDeviceStruct>? devices;

  // Stores action output result for [Custom Action - ble0findDevices] action in Button widget.
  List<BTDeviceStruct>? devicesScanCopy;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
  }
}
