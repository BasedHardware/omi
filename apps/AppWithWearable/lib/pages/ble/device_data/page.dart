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
  Timer? _timer;
  List<String> whispers = [];
  List<String> whispersDiarized = [];

  _initiateTimer() {
    _timer = Timer(const Duration(seconds: 30), () {
      debugPrint('Creating memory from whispers');
      String whispers = this.whispers.join(' ');
      debugPrint('whispers: ${this.whispers.join(' ')}');
      processTranscriptContent(whispers);
      setState(() {
        this.whispers = [];
      });
    });
  }

  @override
  void initState() {
    super.initState();

    // On component load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await actions.bleReceiveWAV(widget.btDevice!, (_) {
        debugPrint("Deepgram Finalized Callback received"); // it's always empty string
        setState(() {
          // Add space for a new entry
          whispers.add('');
        });
        _initiateTimer();
      }, (String transcript) {
        _timer?.cancel();

        // We dont have any whispers yet so we need to create the first one to update
        if (whispers.isEmpty) {
          setState(() {
            whispers.add(transcript);
          });
        } else {
          setState(() {
            whispers[whispers.length - 1] = transcript;
          });
        }
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
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
                  return ListView.separated(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    scrollDirection: Axis.vertical,
                    itemCount: whispers.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 16.0),
                    itemBuilder: (context, whispersListIndex) {
                      final whispersListItem = whispers[whispersListIndex];
                      return Padding(
                        padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
                        child: Text(
                          whispersListItem,
                          style: FlutterFlowTheme.of(context).bodyMedium.override(
                                fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                                letterSpacing: 0.0,
                                useGoogleFonts:
                                    GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
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
