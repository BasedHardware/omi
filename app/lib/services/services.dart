import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_sound/flutter_sound.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/sockets.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/logger.dart';

class ServiceManager {
  late IMicRecorderService _mic;
  late IDeviceService _device;
  late ISocketService _socket;
  late IWalService _wal;
  static ServiceManager? _instance;

  static ServiceManager _create() {
    ServiceManager sm = ServiceManager();
    sm._mic = MicRecorderBackgroundService(runner: BackgroundService());
    sm._device = DeviceService();
    sm._socket = SocketServicePool();
    sm._wal = WalService();

    return sm;
  }

  static ServiceManager instance() {
    if (_instance == null) {
      throw Exception("Service manager is not initiated");
    }

    return _instance!;
  }

  IMicRecorderService get mic => _mic;

  IDeviceService get device => _device;

  ISocketService get socket => _socket;

  IWalService get wal => _wal;

  static Future<void> init() async {
    if (_instance != null) {
      throw Exception("Service manager is initiated");
    }
    _instance = ServiceManager._create();
    await ConnectivityService().init();
  }

  Future<void> start() async {
    _device.start();
    _wal.start();
  }

  void deinit() async {
    ConnectivityService().dispose();
    await _wal.stop();
    _mic.stop();
    _device.stop();
  }
}

enum BackgroundServiceStatus { initiated, running }

@pragma('vm:entry-point')
Future<bool> onIosBackground(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();

  return true;
}

@pragma('vm:entry-point')
Future onStart(ServiceInstance service) async {
  // Recorder
  MicRecorderService? recorder;
  service.on('recorder.start').listen((event) async {
    recorder = MicRecorderService(isInBG: Platform.isAndroid ? true : false);
    recorder?.start(
      onByteReceived: (bytes) {
        Uint8List audioBytes = bytes;
        List<dynamic> audioBytesList = audioBytes.toList();
        service.invoke("recorder.ui.audioBytes", {"data": audioBytesList});
      },
      onStop: () {
        service.invoke("recorder.ui.stateUpdate", {"state": 'stopped'});
      },
      onRecording: () {
        service.invoke("recorder.ui.stateUpdate", {"state": 'recording'});
      },
      onStalled: () {
        service.invoke("recorder.ui.stalled");
      },
    );
  });

  service.on('recorder.stop').listen((event) async {
    service.invoke("recorder.ui.stateUpdate", {"state": 'stopped'});
    recorder?.stop();
  });

  service.on('stop').listen((event) async {
    if (recorder?.status != RecorderServiceStatus.stop) {
      recorder?.stop();
    }
    service.invoke("recorder.ui.stateUpdate", {"state": 'stopped'});
    service.stopSelf();
  });

  // watchdog
  var pongAt = DateTime.now();
  service.on('pong').listen((event) async {
    pongAt = DateTime.now();
  });
  Timer.periodic(const Duration(seconds: 5), (timer) async {
    if (pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 15)))) {
      // retire
      if (recorder?.status != RecorderServiceStatus.stop) {
        recorder?.stop();
      }
      service.invoke("recorder.ui.stateUpdate", {"state": 'stopped'});
      service.stopSelf();
      return;
    }
    service.invoke("ui.ping");
  });
}

class BackgroundService {
  late FlutterBackgroundService _service;
  BackgroundServiceStatus? _status;

  BackgroundServiceStatus? get status => _status;

  Future<void> init() async {
    _service = FlutterBackgroundService();
    _status = BackgroundServiceStatus.initiated;

    await _service.configure(
      iosConfiguration: IosConfiguration(autoStart: false, onForeground: onStart, onBackground: onIosBackground),
      androidConfiguration: AndroidConfiguration(
        autoStart: false,
        onStart: onStart,
        isForegroundMode: true,
        autoStartOnBoot: false,
        foregroundServiceTypes: [AndroidForegroundType.microphone],
      ),
    );

    _status = BackgroundServiceStatus.initiated;
  }

  Future<void> ensureRunning() async {
    await init();
    await start();
  }

  Future<void> start() async {
    _service.startService();

    // status
    if (await _service.isRunning()) {
      _status = BackgroundServiceStatus.running;
    }

    // heartbeat
    _service.on('ui.ping').listen((event) {
      _service.invoke("pong");
    });
  }

  void stop() {
    Logger.debug("invoke stop");
    _service.invoke("stop");
  }

  void onStop(ServiceInstance instance) async {
    _service.invoke("recorder.stateUpdate", {"state": 'stopped'});
    instance.stopSelf();
  }

  void startRecorder({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
  }) {
    StreamSubscription? recordAudioByteStream = _service.on('recorder.ui.audioBytes').listen((event) {
      Uint8List bytes = Uint8List.fromList(event!['data'].cast<int>());
      onByteReceived(bytes);
    });
    StreamSubscription? recordStalledStream;
    if (onStalled != null) {
      recordStalledStream = _service.on('recorder.ui.stalled').listen((event) {
        onStalled();
      });
    }
    StreamSubscription? recordStateStream;
    recordStateStream = _service.on('recorder.ui.stateUpdate').listen((event) {
      if (event!['state'] == 'recording') {
        if (onRecording != null) {
          onRecording();
        }
      } else if (event['state'] == 'initializing') {
        if (onInitializing != null) {
          onInitializing();
        }
      } else if (event['state'] == 'stopped') {
        // Close streams
        recordAudioByteStream.cancel();
        recordStalledStream?.cancel();
        recordStateStream?.cancel();

        // Callback
        if (onStop != null) {
          onStop();
        }
      }
    });

    // tell service > start record
    _service.invoke("recorder.start");
  }

  void stopRecorder() {
    _service.invoke("recorder.stop");
  }
}

enum RecorderServiceStatus { initialising, recording, stop }

abstract class IMicRecorderService {
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
  });
  void stop();
}

class MicRecorderBackgroundService implements IMicRecorderService {
  late BackgroundService _runner;

  MicRecorderBackgroundService({required BackgroundService runner}) {
    _runner = runner;
  }

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
  }) async {
    await _runner.ensureRunning();

    _runner.startRecorder(
      onByteReceived: onByteReceived,
      onRecording: onRecording,
      onStop: onStop,
      onInitializing: onInitializing,
      onStalled: onStalled,
    );

    return;
  }

  @override
  void stop() {
    _runner.stopRecorder();
  }
}

class MicRecorderService implements IMicRecorderService {
  // Window without a single audio byte that counts as a stall.
  // Phone mic at 16 kHz/PCM16 emits ~10 buffer events per second; 3 s of silence
  // is well past any normal jitter and comfortably covers an iOS audio-session
  // interruption (the OS pauses the engine, bytes stop flowing immediately).
  static const Duration _stallThreshold = Duration(seconds: 3);
  static const Duration _stallCheckInterval = Duration(seconds: 1);

  RecorderServiceStatus? _status;

  late FlutterSoundRecorder _recorder;
  late StreamController<Uint8List> _controller;

  Function(Uint8List bytes)? _onByteReceived;
  Function? _onRecording;
  Function? _onStop;
  Function? _onStalled;

  bool _isInBG = false;

  DateTime? _lastByteAt;
  Timer? _stallTimer;
  bool _stallReported = false;

  MicRecorderService({bool isInBG = false}) {
    _recorder = FlutterSoundRecorder();
    _isInBG = isInBG;
  }

  get status => _status;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
  }) async {
    if (_status == RecorderServiceStatus.recording) {
      throw Exception("Recorder is recording, please stop it before start new recording.");
    }
    if (_status == RecorderServiceStatus.initialising) {
      throw Exception("Recorder is initialising");
    }

    _status = RecorderServiceStatus.initialising;

    // callback
    _onByteReceived = onByteReceived;
    _onStop = onStop;
    _onRecording = onRecording;
    _onStalled = onStalled;
    if (_onRecording != null) {
      _onRecording!();
    }

    // new record
    await _recorder.openRecorder(isBGService: _isInBG);
    _controller = StreamController<Uint8List>();

    await _recorder.startRecorder(
      toStream: _controller.sink,
      codec: Codec.pcm16,
      numChannels: 1,
      sampleRate: 16000,
      bufferSize: 8192,
    );
    _lastByteAt = DateTime.now();
    _stallReported = false;
    _controller.stream.listen((buffer) {
      _lastByteAt = DateTime.now();
      _stallReported = false;
      if (_onByteReceived != null) {
        _onByteReceived!(buffer);
      }
    });

    _stallTimer?.cancel();
    _stallTimer = Timer.periodic(_stallCheckInterval, (_) {
      // The stream going silent for longer than the threshold means the native
      // audio engine has stopped delivering bytes — on iOS this happens when
      // AVAudioSession is interrupted (incoming call) and is not resumed.
      if (_stallReported || _lastByteAt == null) return;
      if (DateTime.now().difference(_lastByteAt!) >= _stallThreshold) {
        _stallReported = true;
        _onStalled?.call();
      }
    });

    _status = RecorderServiceStatus.recording;
    return;
  }

  @override
  void stop() {
    _stallTimer?.cancel();
    _stallTimer = null;
    _lastByteAt = null;
    _stallReported = false;

    _recorder.stopRecorder();
    _recorder.closeRecorder();
    _controller.close();

    // callback
    _status = RecorderServiceStatus.stop;
    if (_onStop != null) {
      _onStop!();
    }

    _onByteReceived = null;
    _onStop = null;
    _onRecording = null;
    _onStalled = null;
  }
}
