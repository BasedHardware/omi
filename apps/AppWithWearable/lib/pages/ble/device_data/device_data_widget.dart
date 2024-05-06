import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/actions/actions.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';

import '/backend/schema/structs/index.dart';
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'device_data_model.dart';

export 'device_data_model.dart';

class DeviceDataWidget extends StatefulWidget {
  const DeviceDataWidget({
    super.key,
    required this.btDevice,
  });

  final BTDeviceStruct? btDevice;

  @override
  State<DeviceDataWidget> createState() => _DeviceDataWidgetState();
}

class _DeviceDataWidgetState extends State<DeviceDataWidget> {
  late DeviceDataModel _model;
  Timer? _timer;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  _initiateTimer() {
    _timer = Timer(const Duration(seconds: 30), () {
      debugPrint('Creating memory from whispers');
      String whispers = FFAppState().whispers.join(' ');
      debugPrint('FFAppState().whispers: ${FFAppState().whispers}');
      processTranscriptContent(whispers);
      setState(() {
        FFAppState().whispers = [];
        _model.whispers = [];
      });
    });
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => DeviceDataModel());

    // On component load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      _model.wav = await actions.bleReceiveWAV(widget.btDevice!, (String receivedData) {
        debugPrint("Deepgram Finalized Callback received"); // it's always empty string
        setState(() {
          _model.addToWhispers(receivedData);
          FFAppState().addToWhispers(receivedData);
        });
        _initiateTimer();
      }, (String transcript) {
        _timer?.cancel();

        // We dont have any whispers yet so we need to create the first one to update
        if (_model.whispers.isEmpty) {
          setState(() {
            _model.addToWhispers(transcript);
            FFAppState().addToWhispers(transcript);
          });
        } else {
          setState(() {
            _model.updateWhispersAtIndex(_model.whispers.length - 1, transcript);
            FFAppState().updateWhispersAtIndex(_model.whispers.length - 1, transcript);
          });
        }
      });
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
      alignment: const AlignmentDirectional(0.0, 0.0),
      child: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(),
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
                    separatorBuilder: (_, __) => const SizedBox(height: 16.0),
                    itemBuilder: (context, whispersListIndex) {
                      final whispersListItem = whispersList[whispersListIndex];
                      return Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                        child: Text(
                          whispersListItem,
                          style: FlutterFlowTheme
                              .of(context)
                              .bodyMedium
                              .override(
                            fontFamily: FlutterFlowTheme
                                .of(context)
                                .bodyMediumFamily,
                            letterSpacing: 0.0,
                            useGoogleFonts:
                            GoogleFonts.asMap().containsKey(FlutterFlowTheme
                                .of(context)
                                .bodyMediumFamily),
                          ),
                        ),
                      );
                    },
                  );
                },
              ),
            ].divide(const SizedBox(height: 16.0)),
          ),
        ),
      ),
    );
  }
}
