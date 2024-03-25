import '/components/item_permission_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'permissions_list_widget.dart' show PermissionsListWidget;
import 'package:flutter/material.dart';

class PermissionsListModel extends FlutterFlowModel<PermissionsListWidget> {
  ///  State fields for stateful widgets in this component.

  // Model for item_permission component.
  late ItemPermissionModel itemPermissionModel;
  // State field(s) for Checkbox2 widget.
  bool? checkbox2Value;

  /// Initialization and disposal methods.

  @override
  void initState(BuildContext context) {
    itemPermissionModel = createModel(context, () => ItemPermissionModel());
  }

  @override
  void dispose() {
    itemPermissionModel.dispose();
  }

  /// Action blocks are added here.

  /// Additional helper methods are added here.
}
