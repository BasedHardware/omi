import 'dart:async';

import 'package:collection/collection.dart';
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
  List<String> whispers = [''];
  List<Map<int, String>> whispersDiarized = [{}];

  String _buildDiarizedTranscriptMessage() {
    String transcript = '';
    // go through each speaker starting at 0
    int maxSpeakersCount = whispersDiarized
        .map((e) => e.keys.isEmpty ? 0 : ((e.keys).max + 1))
        .reduce((value, element) => value > element ? value : element);

    debugPrint('Speakers count: $maxSpeakersCount');
    for (int partIdx = 0; partIdx < whispersDiarized.length; partIdx++) {
      var part = whispersDiarized[partIdx];
      if (part.isEmpty) continue;
      for (int speaker = 0; speaker < maxSpeakersCount; speaker++) {
        if (part.containsKey(speaker)) {
          // This part and previous have only 1 speaker, and is the same
          if (partIdx > 0 &&
              whispersDiarized[partIdx - 1].containsKey(speaker) &&
              whispersDiarized[partIdx - 1].length == 1 &&
              part.length == 1) {
            transcript += '${part[speaker]!} ';
          } else {
            transcript += 'Speaker $speaker: ${part[speaker]!} ';
          }
        }
      }
      transcript += '\n';
    }
    return transcript;
  }

  _initiateTimer() {
    _timer = Timer(const Duration(seconds: 5), () {
      debugPrint('Creating memory from whispers');
      // String whispers = this.whispers.join(' ').trim();
      // debugPrint('whispers: ${this.whispers.join(' ')}');
      String transcript = _buildDiarizedTranscriptMessage();
      debugPrint('transcript: \n${transcript.trim()}');
      debugPrint('whispersDiarized: $whispersDiarized');
      processTranscriptContent(transcript);
      setState(() {
        whispers = [''];
        whispersDiarized = [{}];
      });
    });
  }

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await actions.bleReceiveWAV(widget.btDevice!, (_) {
        debugPrint("Deepgram Finalized Callback received");
        setState(() {
          whispers.add(''); // Add space for a new entry
          whispersDiarized.add({});
        });
        _initiateTimer();
      }, (String transcript, Map<int, String> transcriptBySpeaker) {
        _timer?.cancel();
        setState(() {
          whispers[whispers.length - 1] = transcript;
          transcriptBySpeaker.forEach((speaker, transcript) {
            whispersDiarized[whispersDiarized.length - 1][speaker] = transcript;
          });
        });
      });
    });

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();

    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: whispers.length,
      physics: const NeverScrollableScrollPhysics(),
      // TODO: use speaker diarization instead, maybe a sublist?
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
              useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
            ),
          ),
        );
      },
    );
  }
}
