import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/pages/ble/blur/blur_widget.dart';
import '/pages/ble/device_data/widget.dart';
import 'page.dart' show ConnectDeviceWidget;

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

  @override
  void initState(BuildContext context) {
    blurModel = createModel(context, () => BlurModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    rssiUpdateTimer?.cancel();
    blurModel.dispose();
  }
}
