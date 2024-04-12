import 'package:flutter/material.dart';

import '/components/logo/logo_main/logo_main_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'welcome_widget.dart' show WelcomeWidget;

class WelcomeModel extends FlutterFlowModel<WelcomeWidget> {
  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Model for blurBot component.
  late BlurBotModel blurBotModel;
  // Model for logo_main component.
  late LogoMainModel logoMainModel;

  @override
  void initState(BuildContext context) {
    blurBotModel = createModel(context, () => BlurBotModel());
    logoMainModel = createModel(context, () => LogoMainModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    blurBotModel.dispose();
    logoMainModel.dispose();
  }
}
