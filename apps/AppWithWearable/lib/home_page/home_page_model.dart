import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur/blur_widget.dart';
import 'home_page_widget.dart' show HomePageWidget;

class HomePageModel extends FlutterFlowModel<HomePageWidget> {
  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Model for blur component.
  late BlurModel blurModel;

  @override
  void initState(BuildContext context) {
    blurModel = createModel(context, () => BlurModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    blurModel.dispose();
  }
}
