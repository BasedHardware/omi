import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'import_apple_widget.dart' show ImportAppleWidget;
import 'package:flutter/material.dart';

class ImportAppleModel extends FlutterFlowModel<ImportAppleWidget> {
  ///  State fields for stateful widgets in this component.

  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;
  // Stores action output result for [Backend Call - API (Vectorize)] action in Button widget.
  List<double>? vectorized;
  // Stores action output result for [Backend Call - Create Document] action in Button widget.
  MemoriesRecord? createdMemoryManually;
  // Stores action output result for [Backend Call - API (createVectorPinecone)] action in Button widget.
  bool? addedVector;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }

  /// Action blocks are added here.

  Future popupclosing(BuildContext context) async {
    logFirebaseEvent('popupclosing_update_app_state');
    FFAppState().RecordingPopupIsShown = false;
    FFAppState().speechWasActivatedByUser = false;
  }

  /// Additional helper methods are added here.
}
