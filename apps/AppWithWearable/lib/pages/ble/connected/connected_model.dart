import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '../../../widgets/blur_widget.dart';
import 'connected_widget.dart' show ConnectedWidget;

class ConnectedModel extends FlutterFlowModel<ConnectedWidget> {
  ///  Local state fields for this page.

  int? currentRssi;

  double connectedFraction = 0.0;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();

  // Stores action output result for [Custom Action - ble0connectDevice] action in connected widget.
  bool? hasWrite;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
  }
}
