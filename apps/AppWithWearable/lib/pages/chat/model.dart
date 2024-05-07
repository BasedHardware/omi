import '/flutter_flow/flutter_flow_util.dart';
import 'page.dart' show ChatPageWidget;
import 'package:flutter/material.dart';

class ChatModel extends FlutterFlowModel<ChatPageWidget> {
  ///  Local state fields for this page.

  bool showCommandAlertBool = false;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();

  // State field(s) for Column widget.
  ScrollController? columnController;

  // State field(s) for ListView widget.
  ScrollController? listViewController;

  // State field(s) for TextField widget.
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;
  String? Function(BuildContext, String?)? textControllerValidator;

  // Stores action output result for [Backend Call - API (Vectorize)] action in IconButton widget.
  List<double>? vector;

  // Stores action output result for [Backend Call - API (QueryVectors)] action in IconButton widget.
  List? simillarVectors;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {
    columnController = ScrollController();
    listViewController = ScrollController();
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    columnController?.dispose();
    listViewController?.dispose();
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }

  Future pageCommand(BuildContext context) async {}

  Future showCommandAlert(BuildContext context) async {
    showCommandAlertBool = true;
    await Future.delayed(const Duration(milliseconds: 5000));
    showCommandAlertBool = false;
  }
}
