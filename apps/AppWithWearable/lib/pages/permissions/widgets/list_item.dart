import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '/backend/schema/enums/enums.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/permissions_util.dart';

class PermissionItemData {
  final String text;
  final IconData icon;
  final Permission permission;
  bool isGranted;

  PermissionItemData({
    required this.text,
    required this.icon,
    required this.permission,
    required this.isGranted,
  });
}

class PermissionListItem extends StatefulWidget {
  final PermissionItemData permission;

  const PermissionListItem({super.key, required this.permission});

  @override
  State<PermissionListItem> createState() => _PermissionListItemState();
}

class _PermissionListItemState extends State<PermissionListItem> {

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          if (widget.permission.permission == Permission.bluetooth) {
            await requestPermission(bluetoothPermission);
            if (!(await getPermissionStatus(bluetoothPermission))) {
              return;
            }
          } else if (widget.permission.permission == Permission.notifs) {
            await requestPermission(notificationsPermission);
            if (!(await getPermissionStatus(notificationsPermission))) {
              return;
            }
          }

          setState(() {
            widget.permission.isGranted = true;
          });
        },
        child: Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: FlutterFlowTheme.of(context).primary,
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 8.0, 8.0, 8.0),
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
                  alignment: const AlignmentDirectional(0.0, 0.0),
                  child: Stack(
                    children: [
                      Icon(
                        widget.permission.icon,
                        color: FlutterFlowTheme.of(context).secondary,
                        size: 24.0,
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 0.0, 0.0),
                    child: Text(
                      () {
                        if (widget.permission.permission == Permission.microphone) {
                          return 'We need access to your microphone';
                        } else if (widget.permission.permission == Permission.bluetooth) {
                          return 'We need access to your Bluetooth';
                        } else {
                          return 'We need access to send you notifications';
                        }
                      }(),
                      style: FlutterFlowTheme.of(context).bodyMedium.override(
                            fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                            letterSpacing: 0.0,
                            fontWeight: FontWeight.bold,
                            useGoogleFonts:
                                GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                          ),
                    ),
                  ),
                ),
                Builder(
                  builder: (context) {
                    if (widget.permission.isGranted) {
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
