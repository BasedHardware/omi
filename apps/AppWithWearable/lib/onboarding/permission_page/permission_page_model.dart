import '/components/items/permissions_list/permissions_list_widget.dart';
import '/flutter_flow/flutter_flow_animations.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'package:smooth_page_indicator/smooth_page_indicator.dart'
    as smooth_page_indicator;
import 'permission_page_widget.dart' show PermissionPageWidget;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

class PermissionPageModel extends FlutterFlowModel<PermissionPageWidget> {
  ///  State fields for stateful widgets in this page.

  final unfocusNode = FocusNode();
  // State field(s) for PageView widget.
  PageController? pageViewController;

  int get pageViewCurrentIndex => pageViewController != null &&
          pageViewController!.hasClients &&
          pageViewController!.page != null
      ? pageViewController!.page!.round()
      : 0;
  // Model for permissionsList component.
  late PermissionsListModel permissionsListModel;

  @override
  void initState(BuildContext context) {
    permissionsListModel = createModel(context, () => PermissionsListModel());
  }

  @override
  void dispose() {
    unfocusNode.dispose();
    permissionsListModel.dispose();
  }
}
