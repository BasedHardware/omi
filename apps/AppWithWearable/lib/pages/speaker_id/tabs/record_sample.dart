import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/pages/speaker_id/tabs/wave.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';

class RecordSampleTab extends StatefulWidget {
  final BTDeviceStruct? btDevice;
  final SpeakerIdSample sample;
  final int sampleIdx;
  final int totalSamples;
  final VoidCallback onRecordCompleted;

  const RecordSampleTab({
    super.key,
    required this.sample,
    required this.btDevice,
    required this.sampleIdx,
    required this.totalSamples,
    required this.onRecordCompleted,
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
    if ((audioStorage?.audioBytes ?? []).isEmpty) return;
    var bytes = audioStorage!.audioBytes;
    setState(() {
      recording = false;
      speechRecorded = true;
    });
    widget.onRecordCompleted();

    await Future.delayed(const Duration(milliseconds: 500)); // wait for bytes streaming to stream all
    audioBytesStream?.cancel();
    File file = await WavBytesUtil.createWavFile(bytes, filename: '${widget.sample.id}.wav');
    await uploadSample(file, SharedPreferencesUtil().uid); // optimistic request
    // TODO: handle failures + url: null, retry sample
  }

  Future<void> cancelRecording() async {
    audioBytesStream?.cancel();
    audioStorage?.clearAudioBytes();
    setState(() {
      recording = false;
      speechRecorded = false;
      bucket = List.filled(40000, 0).toList(growable: true);
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
    int seconds = (audioStorage?.audioBytes.length ?? 0) ~/ 8000;
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
        recording || speechRecorded
            ? SizedBox(
                height: 80,
                child: Row(
                  children: [
                    const SizedBox(
                      width: 12,
                    ),
                    Text('${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}',
                        style: TextStyle(
                          color: Colors.grey.shade200,
                          fontSize: 18,
                        )),
                    const SizedBox(
                      width: 16,
                    ),
                    Expanded(
                      child: CustomPaint(
                        painter: DashedLinePainter(bucket),
                        child: Container(),
                      ),
                    ),
                    const SizedBox(
                      width: 16,
                    ),
                  ],
                ),
              )
            : const SizedBox(height: 80),
        const SizedBox(height: 12),
        !recording && !speechRecorded
            ? Center(
                child: IconButton(
                  onPressed: startRecording,
                  icon: const Icon(Icons.mic, color: Colors.white, size: 48),
                ),
              )
            : const SizedBox.shrink(),
        recording
            ? Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      onPressed: cancelRecording,
                      icon: const Icon(Icons.stop_circle, color: Colors.red, size: 32),
                    ),
                    const SizedBox(width: 24),
                    IconButton(
                      onPressed: confirmRecording,
                      icon: Icon(Icons.check_circle, color: Colors.grey.shade200, size: 32),
                    ),
                  ],
                ),
              )
            : const SizedBox.shrink(),
        speechRecorded
            ? Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    IconButton(
                      onPressed: cancelRecording,
                      icon: const Icon(Icons.refresh, color: Colors.white, size: 40),
                    ),
                    // const SizedBox(width: 24),
                    // IconButton(
                    //   onPressed: listenRecording,
                    //   icon: Icon(Icons.play_arrow, color: Colors.grey.shade200, size: 32),
                    // ),
                  ],
                ),
              )
            : const SizedBox.shrink(),
        const SizedBox(height: 32),
      ],
    );
  }
}
