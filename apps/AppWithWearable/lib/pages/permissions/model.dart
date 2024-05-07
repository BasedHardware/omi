import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'page.dart' show PermissionPageWidget;

class PermissionPageModel extends FlutterFlowModel<PermissionPageWidget> {
  final unfocusNode = FocusNode();
  PageController? pageViewController;

  int get pageViewCurrentIndex =>
      pageViewController != null && pageViewController!.hasClients && pageViewController!.page != null
          ? pageViewController!.page!.round()
          : 0;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
  }
}
