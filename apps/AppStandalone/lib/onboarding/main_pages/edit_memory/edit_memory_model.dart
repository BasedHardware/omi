import '/backend/backend.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'edit_memory_widget.dart' show EditMemoryWidget;
import 'package:flutter/material.dart';

class EditMemoryModel extends FlutterFlowModel<EditMemoryWidget> {
  ///  Local state fields for this component.

  bool textFieldEmpty = false;

  ///  State fields for stateful widgets in this component.

  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;
  // Stores action output result for [Backend Call - Create Document] action in Button widget.
  MemoriesRecord? createdMemoryManually;
  // Stores action output result for [Backend Call - API (Vectorize)] action in Button widget.
  List<double>? openAIVector;
  // Stores action output result for [Backend Call - API (createVectorPinecone)] action in Button widget.
  dynamic addedVector;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
