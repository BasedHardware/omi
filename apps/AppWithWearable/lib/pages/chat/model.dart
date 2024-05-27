import 'package:friend_private/flutter_flow/flutter_flow_model.dart';

import 'page.dart' show ChatPage;
import 'package:flutter/material.dart';

class ChatModel extends FlutterFlowModel<ChatPage> {
  final unFocusNode = FocusNode();
  ScrollController? columnController;
  ScrollController? listViewController;
  FocusNode? textFieldFocusNode;
  TextEditingController? textController;

  @override
  void initState(BuildContext context) {
    columnController = ScrollController();
    listViewController = ScrollController();
    textFieldFocusNode = FocusNode();
  }

  @override
  void dispose() {
    unFocusNode.dispose();
    columnController?.dispose();
    listViewController?.dispose();
    textFieldFocusNode?.dispose();
    textController?.dispose();
  }
}
