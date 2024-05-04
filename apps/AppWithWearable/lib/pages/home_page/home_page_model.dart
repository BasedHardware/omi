import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/instant_timer.dart';

import 'home_page_widget.dart' show HomePageWidget;
import 'package:flutter/material.dart';

class HomePageModel extends FlutterFlowModel<HomePageWidget> {
  ///  Local state fields for this page.

  bool isShowFullList = true;

  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();

  // Stores action output result for [Backend Call - Create Document] action in homePage widget.
  InstantTimer? instantTimerAction;

  @override
  void initState(BuildContext context) {}

  @override
  void dispose() {
    unfocusNode.dispose();
    instantTimerAction?.cancel();
  }
}
