import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/flutter_flow/instant_timer.dart';
import '/pages/ble/blur/blur_widget.dart';
import '/pages/ble/device_data/device_data_widget.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import 'connect_device_widget.dart' show ConnectDeviceWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class ConnectDeviceModel extends FlutterFlowModel<ConnectDeviceWidget> {
  ///  Local state fields for this page.

  int? currentRssi;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  InstantTimer? rssiUpdateTimer;
  // Stores action output result for [Custom Action - ble0getRssi] action in connectDevice widget.
  int? updatedRssi;
  // Model for blur component.
  late BlurModel blurModel;
  // Model for deviceData component.
  late DeviceDataModel deviceDataModel;

  @override
  void initState(BuildContext context) {
    blurModel = createModel(context, () => BlurModel());
    deviceDataModel = createModel(context, () => DeviceDataModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    rssiUpdateTimer?.cancel();
    blurModel.dispose();
    deviceDataModel.dispose();
  }
}
