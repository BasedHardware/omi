import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/io.dart';

import 'mic_background_service.dart';

// TODO: to be fixed.
// - handle errors processing, no internet or anything
// - Fix backend, use multichannel instead of single channel when recorded from device

mixin PhoneRecorderMixin<T extends StatefulWidget> on State<T> {
  int lastOffset = 0;
  int partNumber = 1;
  int fileCount = 0;
  int iosDuration = 30;
  int androidDuration = 30;
  bool isTranscribing = false;
  RecordingState recordingState = RecordingState.stop;

  // stream related
  List<Uint8List> audioChunks = [];
  int totalBytes = 0;
  var record = AudioRecorder();

  WebsocketConnectionStatus? wsConnectionState2;
  IOWebSocketChannel? websocketChannel2;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) async {
      await listenToBackgroundService();
    });
    super.initState();
  }

  listenToBackgroundService() async {
    if (await FlutterBackgroundService().isRunning()) {
      FlutterBackgroundService().on('audioBytes').listen((event) {
        Uint8List convertedList = Uint8List.fromList(event!['data'].cast<int>());
        if (wsConnectionState2 == WebsocketConnectionStatus.connected) websocketChannel2?.sink.add(convertedList);
      });
      FlutterBackgroundService().on('stateUpdate').listen((event) {
        if (event!['state'] == 'recording') {
          setState(() => recordingState = RecordingState.record);
        } else if (event['state'] == 'initializing') {
          setState(() => recordingState = RecordingState.initialising);
        } else if (event['state'] == 'stopped') {
          setState(() => recordingState = RecordingState.stop);
        }
      });
    }
  }

  streamRecordingOnAndroid(WebsocketConnectionStatus wsConnectionState, IOWebSocketChannel? websocketChannel) async {
    setState(() {
      wsConnectionState2 = wsConnectionState;
      websocketChannel2 = websocketChannel;
    });
    await Permission.microphone.request();
    setState(() => recordingState = RecordingState.initialising);
    await initializeMicBackgroundService();
    startBackgroundService();
    await listenToBackgroundService();
  }

  stopStreamRecordingOnAndroid() {
    stopBackgroundService();
  }

  startStreamRecording(WebsocketConnectionStatus wsConnectionState, IOWebSocketChannel? websocketChannel) async {
    await Permission.microphone.request();
    debugPrint("input device: ${await record.listInputDevices()}");
    InputDevice? inputDevice;
    // if (Platform.isIOS) {
    //   inputDevice = const InputDevice(id: "Built-In Microphone", label: "iPhone Microphone");
    // } else {}
    var stream = await record.startStream(
      RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1, device: inputDevice),
    );
    setState(() => recordingState = RecordingState.record);
    stream.listen((data) async {
      if (wsConnectionState == WebsocketConnectionStatus.connected) websocketChannel?.sink.add(data);
    });
  }

  stopStreamRecording(WebsocketConnectionStatus wsConnectionState, IOWebSocketChannel? websocketChannel) async {
    if (await record.isRecording()) await record.stop();
    setState(() => recordingState = RecordingState.stop);
  }

  @override
  void dispose() async {
    await record.dispose();
    super.dispose();
  }
}
