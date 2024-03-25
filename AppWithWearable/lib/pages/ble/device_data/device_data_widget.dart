import '/backend/api_requests/api_calls.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart' as actions;
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'device_data_model.dart';
export 'device_data_model.dart';

class DeviceDataWidget extends StatefulWidget {
  const DeviceDataWidget({
    super.key,
    required this.btdevice,
  });

  final BTDeviceStruct? btdevice;

  @override
  State<DeviceDataWidget> createState() => _DeviceDataWidgetState();
}

class _DeviceDataWidgetState extends State<DeviceDataWidget> {
  late DeviceDataModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => DeviceDataModel());

    // On component load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      logFirebaseEvent('DEVICE_DATA_deviceData_ON_INIT_STATE');
      while (true) {
        logFirebaseEvent('deviceData_custom_action');
        _model.wav = await actions.bleReceiveWAV(
          widget.btdevice!,
          10,
        );
        logFirebaseEvent('deviceData_show_snack_bar');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Received Wave & processing',
              style: TextStyle(
                color: FlutterFlowTheme.of(context).primary,
              ),
            ),
            duration: Duration(milliseconds: 4000),
            backgroundColor: FlutterFlowTheme.of(context).secondary,
          ),
        );
        if (_model.wav != null && (_model.wav?.bytes?.isNotEmpty ?? false)) {
          logFirebaseEvent('deviceData_backend_call');
          _model.whsiper = await WhisperDCall.call(
            file: _model.wav,
          );
          if ((_model.whsiper?.succeeded ?? true)) {
            logFirebaseEvent('deviceData_show_snack_bar');
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  'Received 10 s WAV',
                  style: TextStyle(
                    color: FlutterFlowTheme.of(context).primary,
                  ),
                ),
                duration: Duration(milliseconds: 4000),
                backgroundColor: FlutterFlowTheme.of(context).secondary,
              ),
            );
            logFirebaseEvent('deviceData_update_component_state');
            setState(() {
              _model.addToWhispers(WhisperDCall.text(
                (_model.whsiper?.jsonBody ?? ''),
              ).toString());
            });
          } else {
            logFirebaseEvent('deviceData_alert_dialog');
            await showDialog(
              context: context,
              builder: (alertDialogContext) {
                return AlertDialog(
                  title: Text('Error'),
                  content: Text((_model.whsiper?.jsonBody ?? '').toString()),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(alertDialogContext),
                      child: Text('Ok'),
                    ),
                  ],
                );
              },
            );
          }
        } else {
          logFirebaseEvent('deviceData_show_snack_bar');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                'No audio yet',
                style: TextStyle(
                  color: FlutterFlowTheme.of(context).primary,
                ),
              ),
              duration: Duration(milliseconds: 4000),
              backgroundColor: FlutterFlowTheme.of(context).secondary,
            ),
          );
        }
      }
    });

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.maybeDispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional(0.0, 0.0),
      child: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: BoxDecoration(),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Builder(
                builder: (context) {
                  final whispersList = _model.whispers.toList();
                  return ListView.separated(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    scrollDirection: Axis.vertical,
                    itemCount: whispersList.length,
                    separatorBuilder: (_, __) => SizedBox(height: 16.0),
                    itemBuilder: (context, whispersListIndex) {
                      final whispersListItem = whispersList[whispersListIndex];
                      return Padding(
                        padding: EdgeInsetsDirectional.fromSTEB(
                            16.0, 0.0, 16.0, 0.0),
                        child: Text(
                          whispersListItem,
                          style: FlutterFlowTheme.of(context).bodyMedium,
                        ),
                      );
                    },
                  );
                },
              ),
            ].divide(SizedBox(height: 16.0)),
          ),
        ),
      ),
    );
  }
}
