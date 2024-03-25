import '/backend/backend.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import 'recording_stopped_widget.dart' show RecordingStoppedWidget;
import 'package:flutter/material.dart';

class RecordingStoppedModel extends FlutterFlowModel<RecordingStoppedWidget> {
  ///  State fields for stateful widgets in this component.

  // Stores action output result for [Backend Call - Create Document] action in Button widget.
  MemoriesRecord? createdIntroNotifCopy;
  InstantTimer? instantTimer13;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    instantTimer13?.cancel();
  }

  /// Action blocks are added here.

  Future popupclosing(BuildContext context) async {
    logFirebaseEvent('popupclosing_update_app_state');
    FFAppState().RecordingPopupIsShown = false;
    FFAppState().speechWasActivatedByUser = false;
  }

  /// Additional helper methods are added here.
}
