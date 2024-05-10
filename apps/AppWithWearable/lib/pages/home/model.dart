import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '../../widgets/blur_widget.dart';
import 'widget.dart';
import 'page.dart' show ConnectDeviceWidget;

class ConnectDeviceModel extends FlutterFlowModel<ConnectDeviceWidget> {
  ///  Local state fields for this page.

  int? currentRssi;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  InstantTimer? rssiUpdateTimer;

  // Stores action output result for [Custom Action - ble0getRssi] action in connectDevice widget.
  int? updatedRssi;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
    rssiUpdateTimer?.cancel();
  }
}
