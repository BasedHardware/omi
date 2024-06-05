import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';

class RecordSampleTab extends StatefulWidget {
  final BTDeviceStruct? btDevice;
  final SpeakerIdSample sample;

  const RecordSampleTab({super.key, required this.sample, required this.btDevice});

  @override
  State<RecordSampleTab> createState() => _RecordSampleTabState();
}

class _RecordSampleTabState extends State<RecordSampleTab> {
  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;

  Future<void> initiateBytesProcessing() async {
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
      }
    });

    audioBytesStream = stream;
    audioStorage = wavBytesUtil;
  }

  @override
  void dispose() {
    audioBytesStream?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      const Text('Say the following sample'),
      Text(
        widget.sample.phrase,
        style: const TextStyle(
          color: Colors.white,
        ),
      ),
      Row(
        children: [
          TextButton(
              onPressed: () {
                initiateBytesProcessing();
              },
              child: const Text(
                'Start recording',
                style: TextStyle(color: Colors.deepPurple),
              )),
          TextButton(
              onPressed: () async {
                File file = await WavBytesUtil.createWavFile(audioStorage?.audioBytes ?? [],
                    filename: '${widget.sample.id}.wav');
                debugPrint('File created: ${file.path}');
                // TODO: upload
                audioBytesStream?.cancel();
              },
              child: const Text(
                'Stop recording',
                style: TextStyle(color: Colors.red),
              ))
        ],
      )
    ]);
  }
}
