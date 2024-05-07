import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'page.dart' show WelcomeWidget;

class WelcomeModel extends FlutterFlowModel<WelcomeWidget> {
  final unfocusNode = FocusNode();
  late BlurBotModel blurBotModel;

  @override
  void initState(BuildContext context) {
    blurBotModel = createModel(context, () => BlurBotModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    blurBotModel.dispose();
  }
}
