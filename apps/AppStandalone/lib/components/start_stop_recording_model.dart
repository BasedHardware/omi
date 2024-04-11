import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import 'start_stop_recording_widget.dart' show StartStopRecordingWidget;
import 'package:flutter/material.dart';

class StartStopRecordingModel
    extends FlutterFlowModel<StartStopRecordingWidget> {
  ///  State fields for stateful widgets in this component.

  InstantTimer? instantTimer1;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    instantTimer1?.cancel();
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
