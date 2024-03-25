import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/components/start_stop_recording_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'chat_widget.dart' show ChatWidget;
import 'package:flutter/material.dart';

class ChatModel extends FlutterFlowModel<ChatWidget> {
  ///  Local state fields for this page.

  bool showCommandAlertBool = false;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // State field(s) for Column widget.
  ScrollController? columnController;
  // State field(s) for ListView widget.
  ScrollController? listViewController;
  // Model for StartStopRecording component.
  late StartStopRecordingModel startStopRecordingModel;
  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;
  // Stores action output result for [Firestore Query - Query a collection] action in IconButton widget.
  List<MemoriesRecord>? latestMemoriesChat2;
  // Stores action output result for [Backend Call - API (Vectorize)] action in IconButton widget.
  ApiCallResponse? vector;
  // Stores action output result for [Backend Call - API (QueryVectors)] action in IconButton widget.
  ApiCallResponse? simillarVectors;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {
    columnController = ScrollController();
    listViewController = ScrollController();
    startStopRecordingModel =
        createModel(context, () => StartStopRecordingModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    columnController?.dispose();
    listViewController?.dispose();
    startStopRecordingModel.dispose();
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }

  /// Action blocks are added here.

  Future pageCommand(BuildContext context) async {}

  Future showCommandAlert(BuildContext context) async {
    logFirebaseEvent('showCommandAlert_update_page_state');
    showCommandAlertBool = true;
    logFirebaseEvent('showCommandAlert_wait__delay');
    await Future.delayed(const Duration(milliseconds: 5000));
    logFirebaseEvent('showCommandAlert_update_page_state');
    showCommandAlertBool = false;
  }

  /// Additional helper methods are added here.
}
