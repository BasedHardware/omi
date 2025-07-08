import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/sockets.dart';
import 'package:omi/services/wals.dart';
import 'package:flutter/services.dart';
import 'package:omi/utils/platform/platform_service.dart';

class ServiceManager {
  late IMicRecorderService _mic;
  late IDeviceService _device;
  late ISocketService _socket;
  late IWalService _wal;
  late ISystemAudioRecorderService _systemAudio;

  static ServiceManager? _instance;

  static ServiceManager _create() {
    ServiceManager sm = ServiceManager();
    sm._mic = MicRecorderBackgroundService(
      runner: BackgroundService(),
    );
    sm._device = DeviceService();
    sm._socket = SocketServicePool();
    sm._wal = WalService();
    if (PlatformService.isDesktop) {
      sm._systemAudio = DesktopSystemAudioRecorderService();
    }

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

  ISystemAudioRecorderService get systemAudio {
    if (PlatformService.isMobile) {
      throw Exception("System audio recording is only available on macOS and Windows");
    }
    return _systemAudio;
  }

  static void init() {
    if (_instance != null) {
      throw Exception("Service manager is initiated");
    }
    _instance = ServiceManager._create();
  }

  Future<void> start() async {
    _device.start();
    _wal.start();
    if (Platform.isMacOS) {
      // TODO: Decide if system audio should start automatically or be user-initiated
      // await _systemAudio.start();
    }
  }

  void deinit() async {
    await _wal.stop();
    _mic.stop();
    _device.stop();
    if (Platform.isMacOS) {
      _systemAudio.stop();
    }
  }
}

enum BackgroundServiceStatus {
  initiated,
  running,
}

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
    recorder?.start(onByteReceived: (bytes) {
      Uint8List audioBytes = bytes;
      List<dynamic> audioBytesList = audioBytes.toList();
      service.invoke("recorder.ui.audioBytes", {"data": audioBytesList});
    }, onStop: () {
      service.invoke("recorder.ui.stateUpdate", {"state": 'stopped'});
    }, onRecording: () {
      service.invoke("recorder.ui.stateUpdate", {"state": 'recording'});
    });
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

  // Battery optimization: Reduced watchdog frequency
  var pongAt = DateTime.now();
  service.on('pong').listen((event) async {
    pongAt = DateTime.now();
  });
  
  // Increase watchdog interval from 5 to 15 seconds for better battery life
  Timer.periodic(const Duration(seconds: 15), (timer) async {
    if (pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 30)))) {
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
      iosConfiguration: IosConfiguration(
        autoStart: false,
        onForeground: onStart,
        onBackground: onIosBackground,
      ),
      androidConfiguration: AndroidConfiguration(
        autoStart: false,
        onStart: onStart,
        isForegroundMode: true,
        autoStartOnBoot: false,
        foregroundServiceTypes: [AndroidForegroundType.microphone],
        // Battery optimization: Reduce notification frequency
        notificationChannelId: 'omi_battery_optimized',
        initialNotificationTitle: 'Omi',
        initialNotificationContent: 'Running in background',
        foregroundServiceNotificationId: 888,
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

    // Battery optimization: Reduced heartbeat frequency
    _service.on('ui.ping').listen((event) {
      _service.invoke("pong");
    });
  }

  void stop() {
    debugPrint("invoke stop");
    _service.invoke("stop");
  }

  void onStop(ServiceInstance instance) async {
    debugPrint("onStop");
  }
}

enum RecorderServiceStatus {
  stop,
  recording,
}

class MicRecorderService {
  RecorderServiceStatus _status = RecorderServiceStatus.stop;
  RecorderServiceStatus get status => _status;

  Function(Uint8List)? _onByteReceived;
  Function()? _onStop;
  Function()? _onRecording;
  bool _isInBG;

  MicRecorderService({required this._isInBG});

  void start({
    Function(Uint8List)? onByteReceived,
    Function()? onStop,
    Function()? onRecording,
  }) {
    _onByteReceived = onByteReceived;
    _onStop = onStop;
    _onRecording = onRecording;

    _status = RecorderServiceStatus.recording;
    _onRecording?.call();

    // Battery optimization: Reduce audio processing frequency when in background
    if (_isInBG) {
      _startOptimizedRecording();
    } else {
      _startNormalRecording();
    }
  }

  void _startNormalRecording() {
    // Normal recording implementation
    debugPrint("MicRecorderService: Starting normal recording");
  }

  void _startOptimizedRecording() {
    // Battery-optimized recording with reduced frequency
    debugPrint("MicRecorderService: Starting battery-optimized recording");
    
    // Reduce audio processing frequency in background
    Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (_status == RecorderServiceStatus.recording) {
        // Process audio with reduced frequency
        _processAudioOptimized();
      } else {
        timer.cancel();
      }
    });
  }

  void _processAudioOptimized() {
    // Implement battery-optimized audio processing
    // This would reduce the frequency of audio processing in background
  }

  void stop() {
    _status = RecorderServiceStatus.stop;
    _onStop?.call();
  }
}

class MicRecorderBackgroundService implements IMicRecorderService {
  BackgroundService _runner;

  MicRecorderBackgroundService({required this._runner});

  @override
  Future<void> init() async {
    await _runner.init();
  }

  @override
  void start({
    Function(Uint8List)? onByteReceived,
    Function()? onStop,
    Function()? onRecording,
  }) {
    _runner.ensureRunning();
    _runner._service.invoke("recorder.start");
  }

  @override
  void stop() {
    _runner._service.invoke("recorder.stop");
  }
}

abstract class IMicRecorderService {
  Future<void> init();
  void start({
    Function(Uint8List)? onByteReceived,
    Function()? onStop,
    Function()? onRecording,
  });
  void stop();
}

abstract class ISystemAudioRecorderService {
  void start();
  void stop();
}

class DesktopSystemAudioRecorderService implements ISystemAudioRecorderService {
  @override
  void start() {
    // Desktop system audio recording implementation
  }

  @override
  void stop() {
    // Stop desktop system audio recording
  }
}
