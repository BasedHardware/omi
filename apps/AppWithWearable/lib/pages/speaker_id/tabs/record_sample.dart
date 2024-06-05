import 'dart:async';
import 'dart:collection';
import 'dart:io';

import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/pages/speaker_id/tabs/wave.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';

class RecordSampleTab extends StatefulWidget {
  final BTDeviceStruct? btDevice;
  final SpeakerIdSample sample;
  final int sampleIdx;
  final int totalSamples;

  const RecordSampleTab({
    super.key,
    required this.sample,
    required this.btDevice,
    required this.sampleIdx,
    required this.totalSamples,
  });

  @override
  State<RecordSampleTab> createState() => _RecordSampleTabState();
}

class _RecordSampleTabState extends State<RecordSampleTab> {
  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;
  bool recording = false;
  bool speechRecorded = false;

  // List<int> bucket = List.filled(40000, 0).toList(growable: true);
  List<int> bucket = List.filled(40000, 0).toList(growable: true);

  Future<void> startRecording() async {
    audioBytesStream?.cancel();
    if (widget.btDevice == null) return;
    WavBytesUtil wavBytesUtil = WavBytesUtil();

    StreamSubscription? stream =
        await getBleAudioBytesListener(widget.btDevice!.id, onAudioBytesReceived: (List<int> value) {
      if (value.isEmpty) return;
      value.removeRange(0, 3);
      for (int i = 0; i < value.length; i += 2) {
        int byte1 = value[i];
        int byte2 = value[i + 1];
        int int16Value = (byte2 << 8) | byte1;
        wavBytesUtil.addAudioBytes([int16Value]);
        if (int16Value < 3000) bucket.add(int16Value);
      }
      if (bucket.length > 40000) {
        setState(() {
          bucket = bucket.sublist(bucket.length - 40000);
        });
      }
    });

    audioBytesStream = stream;
    audioStorage = wavBytesUtil;
    setState(() {
      recording = true;
      speechRecorded = false;
    });
  }

  Future<void> confirmRecording() async {
    var bytes = audioStorage?.audioBytes ?? [];
    debugPrint('Uploading Bytes: ${bytes.length}');
    if (bytes.isEmpty) return;
    await Future.delayed(const Duration(seconds: 2)); // wait for bytes streaming to stream all
    File file = await WavBytesUtil.createWavFile(bytes, filename: '${widget.sample.id}.wav');
    audioBytesStream?.cancel();
    audioStorage?.clearAudioBytes();
    debugPrint('File created: ${file.path}');
    setState(() {
      recording = false;
      speechRecorded = true;
    }); // TODO: add state processing while this happens
    var result = await uploadSample(file, SharedPreferencesUtil().uid);
    if (result) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Sample uploaded ${widget.sample.id}')));
    }
  }

  Future<void> cancelRecording() async {
    audioBytesStream?.cancel();
    audioStorage?.clearAudioBytes();
    setState(() {
      recording = false;
      speechRecorded = false;
    });
  }

  listenRecording() async {}

  @override
  void dispose() {
    audioBytesStream?.cancel();
    audioStorage?.clearAudioBytes();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16.0),
      children: [
        const SizedBox(height: 32),
        Center(
          child: Text(
            'Sample: ${widget.sampleIdx + 1} / ${widget.totalSamples}',
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
          ),
        ),
        const SizedBox(height: 32),
        Center(
          child: Text(
            widget.sample.phrase,
            style: TextStyle(color: Colors.grey.shade200, fontSize: 40, fontWeight: FontWeight.w500),
            textAlign: TextAlign.center,
          ),
        ),
        const SizedBox(height: 80),
        SizedBox(
          height: 80,
          child: Row(
            children: [
              Text('${(audioStorage?.audioBytes.length ?? 0) ~/ 8000}'),
              Expanded(
                child: CustomPaint(
                  painter: DashedLinePainter(bucket),
                  child: Container(),
                ),
              ),
            ],
          ),
        ),
        !recording && !speechRecorded
            ? Center(
                child: IconButton(
                  onPressed: startRecording,
                  icon: const Icon(Icons.mic, color: Colors.white, size: 48),
                ),
              )
            : const SizedBox.shrink(),
        recording
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: cancelRecording,
                    icon: const Icon(Icons.delete, color: Colors.white, size: 32),
                  ),
                  const SizedBox(width: 24),
                  IconButton(
                    onPressed: confirmRecording,
                    icon: const Icon(Icons.send, color: Colors.black87, size: 40),
                  ),
                ],
              )
            : const SizedBox.shrink(),
        speechRecorded
            ? Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: listenRecording,
                    icon: const Icon(Icons.play_arrow, color: Colors.orange, size: 48),
                  ),
                  IconButton(
                    onPressed: cancelRecording,
                    icon: const Icon(Icons.cancel, color: Colors.red, size: 48),
                  ),
                ],
              )
            : const SizedBox.shrink(),
        const SizedBox(height: 32),
      ],
    );
  }
}
