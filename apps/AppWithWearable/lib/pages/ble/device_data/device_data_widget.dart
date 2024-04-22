import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/backend/api_requests/api_calls.dart';
import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
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
            print('Checking for transcript');
      _model.wav = await actions.bleReceiveWAV(
        widget.btdevice!,
        (String receivedData) {
          print("Deepgram Finalized Callback received: $receivedData");
          setState(() {
            _model.addToWhispers(receivedData);
          });
          setState(() {
            FFAppState().addToWhispers(receivedData);
          });
          // You can perform any action using receivedData here
        },
        (String receivedData) {
          print("Deepgram Interim Callback received: $receivedData");

          // We dont have any whispers yet so we need to create the first one to update
          if(_model.whispers.length == 0){
            setState(() {
              _model.addToWhispers(receivedData);
            });
            setState(() {
              FFAppState().addToWhispers(receivedData);
            });
          } else {
               setState(() {
              _model.updateWhispersAtIndex(_model.whispers.length-1, receivedData);
            });
            setState(() {
              FFAppState().updateWhispersAtIndex(_model.whispers.length-1, receivedData);
            });
          }
        

        }
      );
      
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
  context.watch<FFAppState>();

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
                          style: FlutterFlowTheme.of(context)
                              .bodyMedium
                              .override(
                                fontFamily: FlutterFlowTheme.of(context)
                                    .bodyMediumFamily,
                                letterSpacing: 0.0,
                                useGoogleFonts: GoogleFonts.asMap().containsKey(
                                    FlutterFlowTheme.of(context)
                                        .bodyMediumFamily),
                              ),
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
