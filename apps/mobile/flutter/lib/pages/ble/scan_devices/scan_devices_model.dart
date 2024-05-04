import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur/blur_widget.dart';
import 'scan_devices_widget.dart' show ScanDevicesWidget;

class ScanDevicesModel extends FlutterFlowModel<ScanDevicesWidget> {
  ///  Local state fields for this page.

  int? currentRssi;

  double connectedFraction = 0.0;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Model for blur component.
  late BlurModel blurModel;

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
