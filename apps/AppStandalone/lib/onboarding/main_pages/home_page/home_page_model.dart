import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/components/start_stop_recording_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';
import '/flutter_flow/request_manager.dart';

import 'home_page_widget.dart' show HomePageWidget;
import 'package:flutter/material.dart';

class HomePageModel extends FlutterFlowModel<HomePageWidget> {
  ///  Local state fields for this page.

  bool isShowFullList = true;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Stores action output result for [Backend Call - Create Document] action in homePage widget.
  SummariesRecord? summaryCreated;
  InstantTimer? instantTimerAction;
  // Model for StartStopRecording component.
  late StartStopRecordingModel startStopRecordingModel;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {
    startStopRecordingModel =
        createModel(context, () => StartStopRecordingModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    instantTimerAction?.cancel();
    startStopRecordingModel.dispose();

    /// Dispose query cache managers for this widget.
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
