import 'package:flutter/material.dart';

import '/components/items/item_permission/item_permission_widget.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'permissions_list_widget.dart' show PermissionsListWidget;

class PermissionsListModel extends FlutterFlowModel<PermissionsListWidget> {
  ///  State fields for stateful widgets in this component.

  // Model for item_permission component.
  late ItemPermissionModel itemPermissionModel1;
  // Model for item_permission component.
  late ItemPermissionModel itemPermissionModel2;

  @override
  void initState(BuildContext context) {
    itemPermissionModel1 = createModel(context, () => ItemPermissionModel());
    itemPermissionModel2 = createModel(context, () => ItemPermissionModel());
  }

  @override
  void dispose() {
    itemPermissionModel1.dispose();
    itemPermissionModel2.dispose();
  }
}
