import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/permissions_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
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
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 16.0, 0.0, 0.0),
      child: ListView(
        padding: EdgeInsets.zero,
        shrinkWrap: true,
        scrollDirection: Axis.vertical,
        children: [
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
            child: InkWell(
              splashColor: Colors.transparent,
              focusColor: Colors.transparent,
              hoverColor: Colors.transparent,
              highlightColor: Colors.transparent,
              onTap: () async {
                logFirebaseEvent('PERMISSIONS_LIST_Container_o7wmcjef_ON_T');
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
                width: 100.0,
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
                        child: const Stack(
                          children: [
                            Icon(
                              Icons.notifications_active,
                              color: Color(0xFFF7F4F4),
                              size: 24.0,
                            ),
                          ],
                        ),
                      ),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              12.0, 0.0, 0.0, 0.0),
                          child: Text(
                            'We need notifications to send feedback and reminders',
                            style: FlutterFlowTheme.of(context)
                                .bodyMedium
                                .override(
                                  fontFamily: FlutterFlowTheme.of(context)
                                      .bodyMediumFamily,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
                                          .bodyMediumFamily),
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
                                  'PERMISSIONS_LIST_Checkbox_p3ts53ka_ON_TO');
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
          ),
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(8.0, 8.0, 8.0, 8.0),
            child: InkWell(
              splashColor: Colors.transparent,
              focusColor: Colors.transparent,
              hoverColor: Colors.transparent,
              highlightColor: Colors.transparent,
              onTap: () async {
                logFirebaseEvent('PERMISSIONS_LIST_Container_qvy5hm1b_ON_T');
                logFirebaseEvent('Container_request_permissions');
                await requestPermission(microphonePermission);
                logFirebaseEvent('Container_set_form_field');
                setState(() {
                  _model.checkbox2Value = true;
                });
                logFirebaseEvent('Container_update_app_state');
                _model.updatePage(() {});
              },
              child: Container(
                width: 100.0,
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
                        child: const Stack(
                          children: [
                            Icon(
                              Icons.mic,
                              color: Color(0xFFF7F4F4),
                              size: 24.0,
                            ),
                          ],
                        ),
                      ),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsetsDirectional.fromSTEB(
                              12.0, 0.0, 0.0, 0.0),
                          child: Text(
                            'We need access to your microphone',
                            style: FlutterFlowTheme.of(context)
                                .bodyMedium
                                .override(
                                  fontFamily: FlutterFlowTheme.of(context)
                                      .bodyMediumFamily,
                                  fontWeight: FontWeight.bold,
                                  useGoogleFonts: GoogleFonts.asMap()
                                      .containsKey(FlutterFlowTheme.of(context)
                                          .bodyMediumFamily),
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
                          value: _model.checkbox2Value ??= false,
                          onChanged: (newValue) async {
                            setState(() => _model.checkbox2Value = newValue!);
                            if (newValue!) {
                              logFirebaseEvent(
                                  'PERMISSIONS_LIST_Checkbox2_ON_TOGGLE_ON');
                              logFirebaseEvent('Checkbox2_request_permissions');
                              await requestPermission(microphonePermission);
                              logFirebaseEvent('Checkbox2_set_form_field');
                              setState(() {
                                _model.checkbox2Value = true;
                              });
                              logFirebaseEvent('Checkbox2_update_app_state');
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
          ),
        ],
      ),
    );
  }
}
