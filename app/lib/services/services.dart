import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_sound/flutter_sound.dart';

class ServiceManager {
  late MicRecorderService _mic;

  static ServiceManager? _instance;

  static ServiceManager _create() {
    ServiceManager sm = ServiceManager();
    sm._mic = MicRecorderService();
    return sm;
  }

  static ServiceManager instance() {
    if (_instance == null) {
      throw Exception("Service manager is not initiated");
    }

    return _instance!;
  }

  MicRecorderService get mic => _mic;

  static void init() {
    if (_instance != null) {
      throw Exception("Service manager is initiated");
    }
    _instance = ServiceManager._create();
  }

  void deinit() {
    _mic.stop();
  }
}

enum RecorderServiceStatus {
  initiated,
  recording,
  stop,
}

class MicRecorderService {
  late RecorderServiceStatus _status;
  late FlutterSoundRecorder _recorder;
  late StreamController<Uint8List> _controller;

  Function(Uint8List bytes)? _onByteReceived;
  Function? _onRecording;
  Function? _onStop;

  MicRecorderService() {
    _status = RecorderServiceStatus.initiated;
    _recorder = FlutterSoundRecorder();
  }

  get status => _status;

  Future<void> start(
      {required Function(Uint8List bytes) onByteReceived, Function()? onRecording, Function()? onStop}) async {
    if (_status == RecorderServiceStatus.recording) {
      throw Exception("Recorder is recording, please stop it before start new recording.");
    }

    // callback
    _onByteReceived = onByteReceived;
    _onStop = onStop;
    _onRecording = onRecording;

    _status = RecorderServiceStatus.recording;
    if (_onRecording != null) {
      _onRecording!();
    }

    // new record
    await _recorder.openRecorder(isBGService: true);
    _controller = StreamController<Uint8List>();

    await _recorder.startRecorder(
      toStream: _controller.sink,
      codec: Codec.pcm16,
      numChannels: 1,
      sampleRate: 16000,
      bufferSize: 8192,
    );
    _controller.stream.listen((buffer) {
      Uint8List audioBytes = buffer;
      if (_onByteReceived != null) {
        _onByteReceived!(audioBytes);
      }
    });

    return;
  }

  void stop() {
    _recorder.stopRecorder();
    _controller.close();

    // callback
    _status = RecorderServiceStatus.stop;
    if (_onStop != null) {
      _onStop!();
    }

    _onByteReceived = null;
    _onStop = null;
    _onRecording = null;
  }
}
