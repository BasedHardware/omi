import '/components/logo/logo_main/logo_main_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'welcome_widget.dart' show WelcomeWidget;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class WelcomeModel extends FlutterFlowModel<WelcomeWidget> {
  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // Model for blurBot component.
  late BlurBotModel blurBotModel;
  // Model for logo_main component.
  late LogoMainModel logoMainModel;

  /// Initialization and disposal methods.

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

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
