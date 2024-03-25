import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/ble/blur/blur_widget.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import 'connected_widget.dart' show ConnectedWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class ConnectedModel extends FlutterFlowModel<ConnectedWidget> {
  ///  Local state fields for this page.

  int? currentRssi;

  double connectedFraction = 0.0;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Stores action output result for [Custom Action - ble0connectDevice] action in connected widget.
  bool? hasWrite;
  // Model for blur component.
  late BlurModel blurModel;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {
    blurModel = createModel(context, () => BlurModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    blurModel.dispose();
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
