import 'package:flutter/material.dart';

import '/backend/schema/enums/enums.dart';
import '/components/items/item_permission/item_permission_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'permissions_list_model.dart';

export 'permissions_list_model.dart';

class PermissionsListWidget extends StatefulWidget {
  const PermissionsListWidget({super.key});

  @override
  State<PermissionsListWidget> createState() => _PermissionsListWidgetState();
}

class _PermissionsListWidgetState extends State<PermissionsListWidget> {
  late PermissionsListModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => PermissionsListModel());

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.maybeDispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsetsDirectional.fromSTEB(0.0, 16.0, 0.0, 0.0),
      child: ListView(
        padding: EdgeInsets.zero,
        shrinkWrap: true,
        scrollDirection: Axis.vertical,
        children: [
          wrapWithModel(
            model: _model.itemPermissionModel1,
            updateCallback: () => setState(() {}),
            child: ItemPermissionWidget(
              text: 'We need notifications to send feedback and reminders',
              icon: Icon(
                Icons.notifications_active_sharp,
                color: FlutterFlowTheme.of(context).secondary,
                size: 24.0,
              ),
              permission: Permission.notifs,
            ),
          ),
          wrapWithModel(
            model: _model.itemPermissionModel2,
            updateCallback: () => setState(() {}),
            child: ItemPermissionWidget(
              text: 'We need notifications to send feedback and reminders',
              icon: Icon(
                Icons.bluetooth_sharp,
                color: FlutterFlowTheme.of(context).secondary,
                size: 24.0,
              ),
              permission: Permission.bluetooth,
            ),
          ),
        ],
      ),
    );
  }
}
