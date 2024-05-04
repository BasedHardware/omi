import 'package:flutter/material.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur/blur_widget.dart';
import 'find_devices_widget.dart' show FindDevicesWidget;

class FindDevicesModel extends FlutterFlowModel<FindDevicesWidget> {
  ///  Local state fields for this page.

  bool isFetchingDevices = false;

  bool isBluetoothEnabled = false;

  List<BTDeviceStruct> foundDevices = [];
  void addToFoundDevices(BTDeviceStruct item) => foundDevices.add(item);
  void removeFromFoundDevices(BTDeviceStruct item) => foundDevices.remove(item);
  void removeAtIndexFromFoundDevices(int index) => foundDevices.removeAt(index);
  void insertAtIndexInFoundDevices(int index, BTDeviceStruct item) =>
      foundDevices.insert(index, item);
  void updateFoundDevicesAtIndex(
          int index, Function(BTDeviceStruct) updateFn) =>
      foundDevices[index] = updateFn(foundDevices[index]);

  List<BTDeviceStruct> connectedDevices = [];
  void addToConnectedDevices(BTDeviceStruct item) => connectedDevices.add(item);
  void removeFromConnectedDevices(BTDeviceStruct item) =>
      connectedDevices.remove(item);
  void removeAtIndexFromConnectedDevices(int index) =>
      connectedDevices.removeAt(index);
  void insertAtIndexInConnectedDevices(int index, BTDeviceStruct item) =>
      connectedDevices.insert(index, item);
  void updateConnectedDevicesAtIndex(
          int index, Function(BTDeviceStruct) updateFn) =>
      connectedDevices[index] = updateFn(connectedDevices[index]);

  bool isFetchingConnectedDevices = false;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Stores action output result for [Custom Action - ble0getConnectedDevices] action in findDevices widget.
  List<BTDeviceStruct>? fetchedConnectedDevices;
  // Stores action output result for [Custom Action - ble0findDevices] action in findDevices widget.
  List<BTDeviceStruct>? devices;
  // Model for blur component.
  late BlurModel blurModel;
  // Stores action output result for [Custom Action - ble0findDevices] action in Button widget.
  List<BTDeviceStruct>? devicesScanCopy;

  @override
  void initState(BuildContext context) {
    blurModel = createModel(context, () => BlurModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    blurModel.dispose();
  }
}
