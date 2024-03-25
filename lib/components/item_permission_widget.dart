import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/permissions_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'item_permission_model.dart';
export 'item_permission_model.dart';

class ItemPermissionWidget extends StatefulWidget {
  const ItemPermissionWidget({
    super.key,
    required this.text,
    this.icon,
  });

  final String? text;
  final Widget? icon;

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
      padding: const EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          logFirebaseEvent('ITEM_PERMISSION_Container_ipvd5pv6_ON_TA');
          logFirebaseEvent('Container_request_permissions');
          await requestPermission(notificationsPermission);
          logFirebaseEvent('Container_set_form_field');
          setState(() {
            _model.checkboxValue = true;
          });
          logFirebaseEvent('Container_update_app_state');
          _model.updatePage(() {});
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
                      widget.icon!,
                    ],
                  ),
                ),
                Expanded(
                  child: Padding(
                    padding:
                        const EdgeInsetsDirectional.fromSTEB(12.0, 0.0, 0.0, 0.0),
                    child: Text(
                      valueOrDefault<String>(
                        widget.text,
                        '-',
                      ),
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
                Theme(
                  data: ThemeData(
                    checkboxTheme: const CheckboxThemeData(
                      shape: CircleBorder(),
                    ),
                    unselectedWidgetColor:
                        FlutterFlowTheme.of(context).secondary,
                  ),
                  child: Checkbox(
                    value: _model.checkboxValue ??= false,
                    onChanged: (newValue) async {
                      setState(() => _model.checkboxValue = newValue!);
                      if (newValue!) {
                        logFirebaseEvent(
                            'ITEM_PERMISSION_Checkbox_g12sjf20_ON_TOG');
                        logFirebaseEvent('Checkbox_request_permissions');
                        await requestPermission(notificationsPermission);
                        logFirebaseEvent('Checkbox_set_form_field');
                        setState(() {
                          _model.checkboxValue = true;
                        });
                        logFirebaseEvent('Checkbox_update_app_state');
                        _model.updatePage(() {});
                      }
                    },
                    activeColor: FlutterFlowTheme.of(context).primary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
