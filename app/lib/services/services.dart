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
    debugPrint("invoke stop");
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
  }) {
    StreamSubscription? recordAudioByteStream = _service.on('recorder.ui.audioBytes').listen((event) {
      Uint8List bytes = Uint8List.fromList(event!['data'].cast<int>());
      onByteReceived(bytes);
    });
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

enum RecorderServiceStatus {
  initialising,
  recording,
  stop,
}

abstract class IMicRecorderService {
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
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
  }) async {
    await _runner.ensureRunning();

    _runner.startRecorder(
      onByteReceived: onByteReceived,
      onRecording: onRecording,
      onStop: onStop,
      onInitializing: onInitializing,
    );

    return;
  }

  @override
  void stop() {
    _runner.stopRecorder();
  }
}

class MicRecorderService implements IMicRecorderService {
  RecorderServiceStatus? _status;

  late FlutterSoundRecorder _recorder;
  late StreamController<Uint8List> _controller;

  Function(Uint8List bytes)? _onByteReceived;
  Function? _onRecording;
  Function? _onStop;

  bool _isInBG = false;

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
    _controller.stream.listen((buffer) {
      Uint8List audioBytes = buffer;
      if (_onByteReceived != null) {
        _onByteReceived!(audioBytes);
      }
    });

    _status = RecorderServiceStatus.recording;
    return;
  }

  @override
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

abstract class ISystemAudioRecorderService {
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    required Function(Map<String, dynamic> format) onFormatReceived,
    Function()? onRecording,
    Function()? onStop,
    Function(String error)? onError,
    Function(bool wasRecording)? onSystemWillSleep,
    Function(bool nativeIsRecording)? onSystemDidWake,
    Function(bool wasRecording)? onScreenDidLock,
    Function()? onScreenDidUnlock,
    Function(String reason)? onDisplaySetupInvalid,
    Function()? onMicrophoneDeviceChanged,
    Function(String deviceName, double micLevel, double systemAudioLevel)? onMicrophoneStatus,
  });
  void stop();
  // TODO: Add status property
}

class DesktopSystemAudioRecorderService implements ISystemAudioRecorderService {
  static const MethodChannel _channel = MethodChannel('screenCapturePlatform');
  Function(Uint8List bytes)? _onByteReceived;
  Function(Map<String, dynamic> format)? _onFormatReceived;
  Function()? _onRecording;
  Function()? _onStop;
  Function(String error)? _onError;

  // Sleep/wake event callbacks
  Function(bool wasRecording)? _onSystemWillSleep;
  Function(bool nativeIsRecording)? _onSystemDidWake;
  Function(bool wasRecording)? _onScreenDidLock;
  Function()? _onScreenDidUnlock;
  Function(String reason)? _onDisplaySetupInvalid;
  Function()? _onMicrophoneDeviceChanged;
  Function(String deviceName, double micLevel, double systemAudioLevel)? _onMicrophoneStatus;

  // To keep track of recording state from Dart's perspective
  bool _isRecording = false;

  DesktopSystemAudioRecorderService() {
    _channel.setMethodCallHandler(_handleMethodCall);
  }

  Future<void> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case 'audioFrame':
        if (_onByteReceived != null && call.arguments is Uint8List) {
          _onByteReceived!(call.arguments);
        }
        break;
      case 'audioFormat':
        debugPrint("audioFormat: ${call.arguments}");
        if (_onFormatReceived != null && call.arguments is Map) {
          final Map<String, dynamic> format = Map<String, dynamic>.from(call.arguments as Map);
          _onFormatReceived!(format);
        }
        break;
      case 'audioStreamEnded':
        debugPrint("audioStreamEnded");
        _isRecording = false;
        if (_onStop != null) {
          _onStop!();
        }
        _clearCallbacks(); // Clear callbacks after stopping
        break;
      case 'captureError':
      case 'converterError':
        debugPrint("captureError: ${call.arguments}");
        _isRecording = false;
        if (_onError != null && call.arguments is String) {
          _onError!(call.arguments as String);
        }
        if (_onStop != null) {
          _onStop!(); // Also call onStop if there's an error
        }
        _clearCallbacks(); // Clear callbacks after error
        break;
      case 'systemWillSleep':
        await _handleSystemWillSleep(call.arguments);
        break;
      case 'systemDidWake':
        await _handleSystemDidWake(call.arguments);
        break;
      case 'screenDidLock':
        await _handleScreenDidLock(call.arguments);
        break;
      case 'screenDidUnlock':
        await _handleScreenDidUnlock(call.arguments);
        break;
      case 'displaySetupInvalid':
        await _handleDisplaySetupInvalid(call.arguments);
        break;
      case 'microphoneDeviceChanged':
        await _handleMicrophoneDeviceChanged(call.arguments);
        break;
      case 'microphoneStatus':
        if (_onMicrophoneStatus != null && call.arguments is Map) {
          final args = Map<String, dynamic>.from(call.arguments as Map);
          final deviceName = args['deviceName'] as String? ?? 'Unknown Device';
          final micLevel = (args['micLevel'] as num? ?? 0.0).toDouble();
          final systemAudioLevel = (args['systemAudioLevel'] as num? ?? 0.0).toDouble();
          _onMicrophoneStatus!(deviceName, micLevel, systemAudioLevel);
        }
        break;
      default:
        debugPrint('DesktopSystemAudioRecorderService: Unhandled method call: ${call.method}');
    }
  }

  void _clearCallbacks() {
    _onByteReceived = null;
    _onFormatReceived = null;
    _onRecording = null;
    _onStop = null;
    _onError = null;
    _onSystemWillSleep = null;
    _onSystemDidWake = null;
    _onScreenDidLock = null;
    _onScreenDidUnlock = null;
    _onDisplaySetupInvalid = null;
    _onMicrophoneDeviceChanged = null;
    _onMicrophoneStatus = null;
  }

  // Sleep/wake event handlers
  Future<void> _handleSystemWillSleep(dynamic arguments) async {
    final args = arguments as Map<String, dynamic>?;
    final wasRecording = args?['wasRecording'] as bool? ?? false;

    if (_onSystemWillSleep != null) {
      _onSystemWillSleep!(wasRecording);
    }
  }

  Future<void> _handleSystemDidWake(dynamic arguments) async {
    final args = arguments as Map<String, dynamic>?;
    final nativeIsRecording = args?['nativeIsRecording'] as bool? ?? false;

    // Update internal state if there's a mismatch
    if (nativeIsRecording && !_isRecording) {
      _isRecording = true;

      // Notify that recording is active
      if (_onRecording != null) {
        _onRecording!();
      }
    } else if (!nativeIsRecording && _isRecording) {
      _isRecording = false;

      if (_onStop != null) {
        _onStop!();
      }
    }

    if (_onSystemDidWake != null) {
      _onSystemDidWake!(nativeIsRecording);
    }
  }

  Future<void> _handleScreenDidLock(dynamic arguments) async {
    final args = arguments as Map<String, dynamic>?;
    final wasRecording = args?['wasRecording'] as bool? ?? false;

    if (_onScreenDidLock != null) {
      _onScreenDidLock!(wasRecording);
    }
  }

  Future<void> _handleScreenDidUnlock(dynamic arguments) async {
    if (_onScreenDidUnlock != null) {
      _onScreenDidUnlock!();
    }
  }

  Future<void> _handleDisplaySetupInvalid(dynamic arguments) async {
    final args = arguments as Map<String, dynamic>?;
    final reason = args?['reason'] as String? ?? 'Unknown reason';

    _isRecording = false;

    if (_onDisplaySetupInvalid != null) {
      _onDisplaySetupInvalid!(reason);
    }

    if (_onStop != null) {
      _onStop!();
    }
  }

  Future<void> _handleMicrophoneDeviceChanged(dynamic arguments) async {
    if (_onMicrophoneDeviceChanged != null) {
      _onMicrophoneDeviceChanged!();
    }
  }

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    required Function(Map<String, dynamic> format) onFormatReceived,
    Function()? onRecording,
    Function()? onStop,
    Function(String error)? onError,
    Function(bool wasRecording)? onSystemWillSleep,
    Function(bool nativeIsRecording)? onSystemDidWake,
    Function(bool wasRecording)? onScreenDidLock,
    Function()? onScreenDidUnlock,
    Function(String reason)? onDisplaySetupInvalid,
    Function()? onMicrophoneDeviceChanged,
    Function(String deviceName, double micLevel, double systemAudioLevel)? onMicrophoneStatus,
  }) async {
    try {
      bool nativeIsRecording = await _channel.invokeMethod('isRecording') ?? false;

      if (nativeIsRecording && _isRecording) {
        onError?.call("Already recording. Please stop the current recording first.");
        return;
      } else if (nativeIsRecording && !_isRecording) {
        // Native is recording but Flutter lost track - resync the state
        _isRecording = true;

        // Restore callbacks to reconnect with ongoing recording
        _onByteReceived = onByteReceived;
        _onFormatReceived = onFormatReceived;
        _onRecording = onRecording;
        _onStop = onStop;
        _onError = onError;

        // Notify that recording is active
        if (_onRecording != null) {
          _onRecording!();
        }
        return;
      } else if (!nativeIsRecording && _isRecording) {
        // Flutter thinks it's recording but native isn't - reset Flutter state
        _isRecording = false;
      }
    } catch (e) {
      debugPrint("[SystemAudio] Could not check native recording state: $e");
    }

    if (_isRecording) {
      // Potentially call onError or throw if already recording
      onError?.call("Already recording. Please stop the current recording first.");
      return;
    }

    // Store the callbacks
    _onByteReceived = onByteReceived;
    _onFormatReceived = onFormatReceived;
    _onRecording = onRecording;
    _onStop = onStop;
    _onError = onError;
    _onSystemWillSleep = onSystemWillSleep;
    _onSystemDidWake = onSystemDidWake;
    _onScreenDidLock = onScreenDidLock;
    _onScreenDidUnlock = onScreenDidUnlock;
    _onDisplaySetupInvalid = onDisplaySetupInvalid;
    _onMicrophoneDeviceChanged = onMicrophoneDeviceChanged;
    _onMicrophoneStatus = onMicrophoneStatus;

    try {
      await _channel.invokeMethod('start');
      _isRecording = true;
      if (_onRecording != null) {
        _onRecording!();
      }
    } catch (e) {
      debugPrint("Error starting system audio recording: $e");
      _isRecording = false;
      if (_onError != null) {
        _onError!(e.toString());
      }
      if (_onStop != null) {
        _onStop!();
      }
      _clearCallbacks();
    }
  }

  @override
  void stop() {
    if (!_isRecording) {
      // Optionally, log or call onError if trying to stop when not recording
      // _onError?.call("Not recording.");
      // return;
    }
    try {
      _channel.invokeMethod('stop');
      // _isRecording will be set to false and _onStop called
      // when 'audioStreamEnded' is received from native code.
      // If the invokeMethod 'stop' itself fails, we might not get 'audioStreamEnded'.
    } catch (e) {
      debugPrint("Error stopping system audio recording: \$e");
      _isRecording = false;
      if (_onError != null) {
        _onError!(e.toString());
      }
      if (_onStop != null) {
        _onStop!();
      }
      _clearCallbacks();
    }
  }
}
