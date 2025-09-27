import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:frame_sdk/frame_sdk.dart';
import 'package:omi/services/devices/communication/device_communicator.dart';

class FrameCommunicator extends DeviceCommunicator {
  final String _deviceId;
  final StreamController<Map<String, dynamic>> _messageController;
  final StreamController<DeviceConnectionState> _connectionStateController;

  Frame? _frame;
  bool? _isLooping;

  FrameCommunicator(this._deviceId)
      : _messageController = StreamController<Map<String, dynamic>>.broadcast(),
        _connectionStateController = StreamController<DeviceConnectionState>.broadcast();

  @override
  String get deviceId => _deviceId;

  @override
  DeviceConnectionState get connectionState =>
      _frame?.isConnected == true ? DeviceConnectionState.connected : DeviceConnectionState.disconnected;

  @override
  Stream<DeviceConnectionState> get connectionStateStream => _connectionStateController.stream;

  @override
  Future<void> connect() async {
    _frame ??= Frame();
    _frame!.useLibrary = false;

    final connected = await _frame!.connectToDevice(_deviceId);
    if (connected) {
      _connectionStateController.add(DeviceConnectionState.connected);
      await _afterConnect();
    } else {
      _connectionStateController.add(DeviceConnectionState.disconnected);
    }
  }

  @override
  Future<void> disconnect() async {
    if (_frame != null) {
      _frame!.bluetooth.disconnect();
      _connectionStateController.add(DeviceConnectionState.disconnected);
    }
  }

  @override
  Future<bool> isConnected() async {
    return _frame?.isConnected == true;
  }

  @override
  Future<Map<String, dynamic>?> sendCommand(String command, [Map<String, dynamic>? params]) async {
    switch (command) {
      case 'getBattery':
        return await _getBatteryLevel();
      case 'getAudioCodec':
        return {'codec': 'pcm8'}; // Frame always uses PCM8
      case 'startAudioStream':
        return await _startAudioStream(params?['onAudioReceived']);
      case 'sendLuaCommand':
        return await _sendLuaCommand(params?['command'] ?? '');
      case 'getFrameInfo':
        return await _getFrameInfo();
      case 'startCamera':
        return await _startCamera();
      case 'stopCamera':
        return await _stopCamera();
      case 'getFromLoop':
        return await _getFromLoop(params?['key'] ?? '');
      default:
        return null;
    }
  }

  @override
  Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

  @override
  Future<void> dispose() async {
    if (_frame != null) {
      _frame!.bluetooth.disconnect();
    }
    await _messageController.close();
    await _connectionStateController.close();
  }

  // Frame-specific methods
  Future<void> _afterConnect() async {
    if (_frame == null || _frame!.isConnected == false) return;

    // Set up debug subscription
    _frame!.bluetooth.stringResponse.listen((data) {
      debugPrint("Frame printed: $data");
    });

    await _setTimeOnFrame();

    // Check if frame is loaded and running
    bool isLoaded = false;
    bool isRunning = false;

    if (_isLooping == false) {
      try {
        final deviceframeLibHash = await _frame!.evaluate("frameLibHash");
        isLoaded = deviceframeLibHash.isNotEmpty;
      } catch (e) {
        isLoaded = false;
      }
      isRunning = false;
    } else if (_isLooping == true) {
      final deviceframeLibHashResult = await _getFromLoop("frameLibHash");
      final deviceframeLibHash = deviceframeLibHashResult['value'];
      if (deviceframeLibHash == null || deviceframeLibHash.isEmpty) {
        isLoaded = false;
        isRunning = false;
      } else {
        isLoaded = true;
        final loopStatusResult = await _getFromLoop("loopStatus");
        final loopStatus = loopStatusResult['value'];
        isRunning = loopStatus == "1";
      }
    }

    if (isRunning && isLoaded) {
      await _sendHeartbeat();
      await _sendUntilEchoed("MIC START");
      await _sendUntilEchoed("CAMERA START");
    } else if (!isLoaded) {
      // Load main.lua (this would need the actual content)
      debugPrint("Frame needs to be loaded with main.lua");
    } else if (isLoaded && !isRunning) {
      await _frame!.bluetooth.sendBreakSignal();
      await _setTimeOnFrame();
      await _frame!.runLua("start()");
    }
  }

  Future<Map<String, dynamic>> _getBatteryLevel() async {
    if (_frame == null || _frame!.isConnected == false) return {'level': -1};

    try {
      final batteryLevel = await _frame!.evaluate("frame.battery_level()");
      return {'level': int.parse(batteryLevel.toString())};
    } catch (e) {
      return {'level': -1};
    }
  }

  Future<Map<String, dynamic>> _startAudioStream(Function(List<int>)? onAudioReceived) async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'success': false, 'error': 'Frame not connected'};
    }

    try {
      await _sendUntilEchoed("MIC START");

      // Listen for audio data
      _frame!.bluetooth.getDataWithPrefix(0xEE).listen((value) {
        _isLooping = true;
        if (value.isNotEmpty) {
          onAudioReceived?.call(value);
          _messageController.add({
            'type': 'audioData',
            'data': value,
            'timestamp': DateTime.now().millisecondsSinceEpoch,
          });
        }
      });

      return {'success': true};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _sendLuaCommand(String command) async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'success': false, 'error': 'Frame not connected'};
    }

    try {
      await _frame!.runLua(command);
      return {'success': true};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _getFrameInfo() async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'info': {}};
    }

    try {
      final firmwareVersion = await _frame!.evaluate("frame.FIRMWARE_VERSION");
      final batteryLevel = await _frame!.evaluate("frame.battery_level()");

      return {
        'info': {
          'firmwareVersion': firmwareVersion.toString(),
          'batteryLevel': int.parse(batteryLevel.toString()),
          'isLooping': _isLooping,
        }
      };
    } catch (e) {
      return {'info': {}};
    }
  }

  Future<Map<String, dynamic>> _startCamera() async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'success': false, 'error': 'Frame not connected'};
    }

    try {
      await _sendUntilEchoed("CAMERA START");
      return {'success': true};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _stopCamera() async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'success': false, 'error': 'Frame not connected'};
    }

    try {
      await _sendUntilEchoed("CAMERA STOP");
      return {'success': true};
    } catch (e) {
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _getFromLoop(String key) async {
    if (_frame == null || _frame!.isConnected == false) {
      return {'value': null};
    }

    try {
      final value = await _getFromLoopInternal(key);
      return {'value': value};
    } catch (e) {
      return {'value': null};
    }
  }

  Future<String> _getFromLoopInternal(String key, {Duration timeout = const Duration(seconds: 5)}) async {
    int prefix = switch (key) {
      "loopStatus" => 0xE1,
      "micState" => 0xE2,
      "cameraState" => 0xE3,
      "frameLibHash" => 0xE4,
      _ => throw Exception("Invalid key: $key"),
    };

    final futureResult = _frame!.bluetooth.getDataWithPrefix(prefix).first.timeout(timeout);

    if (!await _sendUntilEchoed("GET $key", maxAttempts: 1, timeout: timeout)) {
      return '';
    }

    try {
      final result = await futureResult;
      final value = utf8.decode(result);
      _isLooping = true;
      return value;
    } catch (e) {
      return '';
    }
  }

  Future<void> _sendHeartbeat() async {
    if (_frame == null) return;

    debugPrint("Sending heartbeat to frame");
    final heartbeatBytes = utf8.encode("HEARTBEAT");
    await _frame!.bluetooth.sendData(heartbeatBytes);
  }

  Future<bool> _sendUntilEchoed(String data,
      {int maxAttempts = 3, Duration timeout = const Duration(seconds: 10)}) async {
    if (_frame == null) return false;

    final bytesToSend = utf8.encode(data);

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        final future =
            _frame!.bluetooth.stringResponse.firstWhere((element) => element == "ECHO:$data").timeout(timeout);
        await _frame!.bluetooth.sendData(bytesToSend);
        await future;
        return true;
      } catch (e) {
        if (e is TimeoutException) {
          debugPrint("Timeout occurred while waiting for echo of $data. Attempt $attempt of $maxAttempts");
          if (attempt == maxAttempts) {
            debugPrint("Failed to receive echo for $data after $maxAttempts attempts");
            return false;
          }
        } else {
          debugPrint("Error sending $data to frame: $e");
          return false;
        }
      }
    }
    return false;
  }

  Future<void> _setTimeOnFrame() async {
    if (_frame == null) return;

    if (_isLooping == true) {
      String utcUnixEpochTime = (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000).toString();
      String timeZoneOffset = DateTime.now().timeZoneOffset.inMinutes > 0 ? '+' : '-';
      timeZoneOffset +=
          '${DateTime.now().timeZoneOffset.inHours.abs().toString().padLeft(2, '0')}:${(DateTime.now().timeZoneOffset.inMinutes.abs() % 60).toString().padLeft(2, '0')}';
      await _sendUntilEchoed("timeUtc=$utcUnixEpochTime");
      await _sendUntilEchoed("timeZone=$timeZoneOffset");
    } else if (_isLooping == false) {
      _frame!.setTimeOnFrame(checked: false);
    }
  }
}
