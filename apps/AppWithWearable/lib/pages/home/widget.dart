import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/utils/actions/ble_receive_w_a_v.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';
import 'package:web_socket_channel/io.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';

class DeviceDataWidget extends StatefulWidget {
  const DeviceDataWidget({
    super.key,
    required this.btDevice,
  });

  final BTDeviceStruct? btDevice;

  @override
  State<DeviceDataWidget> createState() => DeviceDataWidgetState();
}

class DeviceDataWidgetState extends State<DeviceDataWidget> {
  Timer? _timer;

  // List<String> whispers = [''];
  List<Map<int, String>> whispersDiarized = [{}];
  IOWebSocketChannel? channel;
  StreamSubscription? streamSubscription;
  AudioStorage? audioStorage;

  String _buildDiarizedTranscriptMessage() {
    int totalSpeakers = whispersDiarized
        .map((e) => e.keys.isEmpty ? 0 : ((e.keys).max + 1))
        .reduce((value, element) => value > element ? value : element);

    debugPrint('Speakers count: $totalSpeakers');

    String transcript = '';
    for (int partIdx = 0; partIdx < whispersDiarized.length; partIdx++) {
      var part = whispersDiarized[partIdx];
      if (part.isEmpty) continue;
      for (int speaker = 0; speaker < totalSpeakers; speaker++) {
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
    _timer = Timer(const Duration(seconds: 30), () async {
      debugPrint('Creating memory from whispers');
      String transcript = _buildDiarizedTranscriptMessage();
      debugPrint('Transcript: \n${transcript.trim()}');
      File file = await audioStorage!.createWavFile();
      String? fileName = await uploadFile(file);
      processTranscriptContent(transcript, fileName);
      setState(() {
        whispersDiarized = [{}];
      });
      audioStorage?.clearAudioBytes();
    });
  }

  @override
  void initState() {
    super.initState();
    initBleConnection();
  }

  void initBleConnection() async {
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      Tuple3<IOWebSocketChannel?, StreamSubscription?, AudioStorage> data = await bleReceiveWAV(widget.btDevice!, (_) {
        debugPrint("Deepgram Finalized Callback received");
        setState(() {
          whispersDiarized.add({});
        });
        _initiateTimer();
      }, (String transcript, Map<int, String> transcriptBySpeaker) {
        _timer?.cancel();
        var copy = whispersDiarized[whispersDiarized.length - 1];
        transcriptBySpeaker.forEach((speaker, transcript) {
          copy[speaker] = transcript;
        });
        setState(() {
          whispersDiarized[whispersDiarized.length - 1] = copy;
        });
      });
      channel = data.item1;
      streamSubscription = data.item2;
      audioStorage = data.item3;
    });
  }

  void resetState({bool resetBLEConnection = true}) {
    streamSubscription?.cancel();
    channel?.sink.close();
    setState(() {
      whispersDiarized = [{}];
      _timer?.cancel();
      if (resetBLEConnection) {
        initBleConnection();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
    var filteredNotEmptyWhispers = whispersDiarized.where((e) => e.isNotEmpty).toList();
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: filteredNotEmptyWhispers.length,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        final data = filteredNotEmptyWhispers[idx];
        String transcriptItem = '';
        for (int speaker = 0; speaker < data.length; speaker++) {
          if (data.containsKey(speaker)) {
            transcriptItem += 'Speaker $speaker: ${data[speaker]!} ';
          }
        }
        return Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: Text(
            transcriptItem,
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
