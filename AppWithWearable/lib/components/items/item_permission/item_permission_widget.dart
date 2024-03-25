import '/backend/schema/enums/enums.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/permissions_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'item_permission_model.dart';
export 'item_permission_model.dart';

class ItemPermissionWidget extends StatefulWidget {
  const ItemPermissionWidget({
    super.key,
    required this.text,
    this.icon,
    required this.permission,
  });

  final String? text;
  final Widget? icon;
  final Permission? permission;

  @override
  State<ItemPermissionWidget> createState() => _ItemPermissionWidgetState();
}

class _ItemPermissionWidgetState extends State<ItemPermissionWidget> {
  late ItemPermissionModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ItemPermissionModel());

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
      padding: EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          logFirebaseEvent('ITEM_PERMISSION_Container_ipvd5pv6_ON_TA');
          if (widget.permission == Permission.bluetooth) {
            logFirebaseEvent('Container_request_permissions');
            await requestPermission(bluetoothPermission);
            if (!(await getPermissionStatus(bluetoothPermission))) {
              return;
            }
          } else if (widget.permission == Permission.notifs) {
            logFirebaseEvent('Container_request_permissions');
            await requestPermission(notificationsPermission);
            if (!(await getPermissionStatus(notificationsPermission))) {
              return;
            }
          }

          logFirebaseEvent('Container_update_component_state');
          setState(() {
            _model.isOn = true;
          });
        },
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: FlutterFlowTheme.of(context).primary,
          ),
          child: Padding(
            padding: EdgeInsetsDirectional.fromSTEB(16.0, 8.0, 8.0, 8.0),
            child: Row(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  width: 36.0,
                  height: 36.0,
                  decoration: BoxDecoration(
                    color: FlutterFlowTheme.of(context).primary,
                    shape: BoxShape.circle,
                  ),
                  alignment: AlignmentDirectional(0.0, 0.0),
                  child: Stack(
                    children: [
                      widget.icon!,
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding:
                        EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 0.0, 0.0),
                    child: Text(
                      () {
                        if (widget.permission == Permission.microphone) {
                          return 'We need access to your microphone';
                        } else if (widget.permission == Permission.bluetooth) {
                          return 'We need access to send you notifications.';
                        } else {
                          return 'We need access to your microphone';
                        }
                      }(),
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                            fontFamily:
                                FlutterFlowTheme.of(context).bodyMediumFamily,
                            fontWeight: FontWeight.bold,
                            useGoogleFonts: GoogleFonts.asMap().containsKey(
                                FlutterFlowTheme.of(context).bodyMediumFamily),
                          ),
                    ),
                  ),
                ),
                Builder(
                  builder: (context) {
                    if (_model.isOn) {
                      return Icon(
                        Icons.check_circle,
                        color: FlutterFlowTheme.of(context).secondary,
                        size: 24.0,
                      );
                    } else {
                      return Icon(
                        Icons.circle_outlined,
                        color: FlutterFlowTheme.of(context).secondary,
                        size: 24.0,
                      );
                    }
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
