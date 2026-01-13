import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:frame_sdk/bluetooth.dart';
import 'package:frame_sdk/frame_sdk.dart';
import 'package:omi/gen/assets.gen.dart';

import 'device_transport.dart';

class FrameTransport extends DeviceTransport {
  final String _deviceId;
  final StreamController<DeviceTransportState> _connectionStateController;
  final Map<String, StreamController<List<int>>> _streamControllers = {};

  Frame? _frame;
  DeviceTransportState _state = DeviceTransportState.disconnected;
  bool? _isLooping;
  int? _batteryLevel;

  StreamSubscription? _heartbeatSubscription;
  StreamSubscription<String>? _debugSubscription;

  FrameTransport(this._deviceId) : _connectionStateController = StreamController<DeviceTransportState>.broadcast();

  @override
  String get deviceId => _deviceId;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  @override
  Future<void> connect({bool autoConnect = false}) async {
    if (_state == DeviceTransportState.connected) {
      return;
    }

    _updateState(DeviceTransportState.connecting);

    try {
      _frame ??= Frame();
      _frame!.useLibrary = false;

      final connected = await _frame!.connectToDevice(_deviceId);
      if (connected) {
        _updateState(DeviceTransportState.connected);
        await _afterConnect();
      } else {
        _updateState(DeviceTransportState.disconnected);
        throw Exception('Failed to connect to Frame device');
      }
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  Future<void> _afterConnect() async {
    if (_frame == null || !_frame!.isConnected) {
      debugPrint("Frame is not connected in afterConnect!");
      return;
    }

    if (_debugSubscription != null) {
      _debugSubscription!.cancel();
    }
    _debugSubscription = _frame!.bluetooth.stringResponse.listen((data) {
      debugPrint("Frame printed: $data");
    });

    await _setTimeOnFrame();

    // Load Lua script and initialize Frame
    await _loadFrameLibrary();

    // Setup heartbeat
    await _setupHeartbeat();

    // Get device info
    if (_isLooping == null || _isLooping == false) {
      try {
        _batteryLevel = int.parse(await _frame!.evaluate("frame.battery_level()"));
        _isLooping = false;
      } catch (e) {
        debugPrint('Frame Transport: Error getting device info: $e');
      }
    }
  }

  Future<void> _loadFrameLibrary() async {
    bool isLoaded = false;
    bool isRunning = false;
    final String mainLuaContent =
        (await rootBundle.loadString(Assets.deviceAssets.frameLib)).replaceAll("\t", "").replaceAll("\n\n", "\n");
    final int frameLibHash = mainLuaContent.hashCode;

    if (_isLooping == false) {
      final deviceframeLibHash = await _frame!.evaluate("frameLibHash");
      isLoaded = deviceframeLibHash == frameLibHash.toString();
      isRunning = false;
    } else if (_isLooping == true) {
      final deviceframeLibHash = await _getFromLoop("frameLibHash");
      if (deviceframeLibHash == null) {
        isLoaded = false;
        isRunning = false;
      } else {
        isLoaded = deviceframeLibHash == frameLibHash.toString();
        isRunning = await _getFromLoop("loopStatus") == "1";
      }
    } else {
      var deviceframeLibHash = await _getFromLoop("frameLibHash");
      if (deviceframeLibHash == null) {
        deviceframeLibHash = await _frame!.evaluate("frameLibHash");
        if (deviceframeLibHash is int) {
          deviceframeLibHash = deviceframeLibHash.toString();
          _isLooping = false;
          isRunning = false;
        }
      } else {
        _isLooping = true;
        isRunning = await _getFromLoop("loopStatus") == "1";
      }
      isLoaded = deviceframeLibHash == frameLibHash.toString();
    }

    if (isRunning && isLoaded) {
      await _sendHeartbeat();
      await _sendUntilEchoed("MIC START");
      await _sendUntilEchoed("CAMERA START");
    } else if (!isLoaded) {
      await _frame!.bluetooth.sendBreakSignal();
      debugPrint("About to send main.lua to frame, length = ${mainLuaContent.length}");
      try {
        await _frame!.files.writeFile("main.lua", utf8.encode("$mainLuaContent\nframeLibHash = $frameLibHash\nstart()"),
            checked: true);
        debugPrint("Sent main.lua to frame");
        await _frame!.bluetooth.sendResetSignal();
      } catch (e) {
        debugPrint("Error sending main.lua to frame: $e");
      }
      await _setTimeOnFrame();
    } else if (isLoaded && !isRunning) {
      await _frame!.bluetooth.sendBreakSignal();
      debugPrint("Frame already loaded, running start()");
      await _setTimeOnFrame();
      await _frame!.runLua("start()");
    }
    await Future.delayed(const Duration(milliseconds: 1000));
  }

  Future<void> _setupHeartbeat() async {
    final heartbeatStream = Stream.periodic(const Duration(seconds: 5));
    _heartbeatSubscription = heartbeatStream.listen((_) {
      _sendHeartbeat();
    });
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) {
      return;
    }

    _updateState(DeviceTransportState.disconnecting);

    try {
      // Cancel subscriptions
      _heartbeatSubscription?.cancel();
      _debugSubscription?.cancel();

      _frame?.bluetooth.disconnect();

      // Close all stream controllers
      for (final controller in _streamControllers.values) {
        await controller.close();
      }
      _streamControllers.clear();

      _updateState(DeviceTransportState.disconnected);
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<bool> isConnected() async {
    return _frame?.isConnected == true;
  }

  @override
  Future<bool> ping() async {
    return await isConnected();
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    final key = '$serviceUuid:$characteristicUuid';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _setupFrameListener(serviceUuid, characteristicUuid, key);
    }

    return _streamControllers[key]!.stream;
  }

  Future<void> _setupFrameListener(String serviceUuid, String characteristicUuid, String key) async {
    if (_frame == null || !_frame!.isConnected) {
      return;
    }

    try {
      if (serviceUuid.contains('audio') || characteristicUuid.contains('audio')) {
        // Audio data stream from Frame (prefix 0xEE)
        _frame!.bluetooth.getDataWithPrefix(0xEE).listen((value) {
          _isLooping = true;
          if (_streamControllers[key] != null && !_streamControllers[key]!.isClosed) {
            _streamControllers[key]!.add(value);
          }
        });
      } else if (serviceUuid.contains('battery') || characteristicUuid.contains('battery')) {
        // Battery level stream from Frame (prefix 0xCC)
        _frame!.bluetooth.getDataWithPrefix(0xCC).listen((value) {
          _isLooping = true;
          if (_streamControllers[key] != null && !_streamControllers[key]!.isClosed && value.isNotEmpty) {
            final currentLevel = value[0];
            if (currentLevel != _batteryLevel) {
              _batteryLevel = currentLevel;
              _streamControllers[key]!.add([currentLevel]);
            }
          }
        });
      } else if (serviceUuid.contains('image') || characteristicUuid.contains('image')) {
        // Image data stream from Frame
        _frame!.bluetooth.getDataOfType(FrameDataTypePrefixes.photoData).listen((value) {
          if (_streamControllers[key] != null && !_streamControllers[key]!.isClosed) {
            _streamControllers[key]!.add(value);
          }
        });
      }
    } catch (e) {
      debugPrint('Frame Transport: Failed to setup listener: $e');
    }
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (_frame == null || !_frame!.isConnected) {
      return [];
    }

    try {
      if (serviceUuid.contains('battery') || characteristicUuid.contains('battery')) {
        if (_batteryLevel != null) {
          return [_batteryLevel!];
        }

        try {
          final batteryLevel = await _frame!.evaluate("frame.battery_level()");
          _batteryLevel = int.parse(batteryLevel.toString());
          return [_batteryLevel!];
        } catch (e) {
          return [-1];
        }
      } else if (serviceUuid.contains('firmware') || characteristicUuid.contains('firmware')) {
        try {
          final firmware = await _frame!.evaluate("frame.FIRMWARE_VERSION");
          return utf8.encode(firmware.toString());
        } catch (e) {
          return [];
        }
      }

      return [];
    } catch (e) {
      debugPrint('Frame Transport: Failed to read characteristic: $e');
      return [];
    }
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    if (_frame == null || !_frame!.isConnected) {
      throw Exception('Frame device not connected');
    }

    try {
      // Map BLE-like writes to Frame SDK commands
      if (serviceUuid.contains('camera') || characteristicUuid.contains('camera')) {
        if (data.isNotEmpty) {
          if (data[0] == 0x01) {
            // Start camera
            await _sendUntilEchoed("CAMERA START");
          } else if (data[0] == 0x00) {
            // Stop camera
            await _sendUntilEchoed("CAMERA STOP");
          }
        }
      } else if (serviceUuid.contains('audio') || characteristicUuid.contains('audio')) {
        if (data.isNotEmpty) {
          if (data[0] == 0x01) {
            // Start audio
            await _sendUntilEchoed("MIC START");
          } else if (data[0] == 0x00) {
            // Stop audio
            await _sendUntilEchoed("MIC STOP");
          }
        }
      } else {
        final command = String.fromCharCodes(data);
        await _sendUntilEchoed(command);
      }
    } catch (e) {
      debugPrint('Frame Transport: Failed to write characteristic: $e');
      rethrow;
    }
  }

  Future<bool> sendCommand(String command) async {
    if (_frame == null || !_frame!.isConnected) {
      return false;
    }

    try {
      await _frame!.bluetooth.sendData(Uint8List.fromList(command.codeUnits));
      return true;
    } catch (e) {
      debugPrint('Frame Transport: Error sending command: $e');
      return false;
    }
  }

  Future<String?> getBatteryLevel() async {
    if (_frame == null || !_frame!.isConnected) {
      return null;
    }

    try {
      final batteryLevel = await _frame!.getBatteryLevel();
      return batteryLevel.toString();
    } catch (e) {
      debugPrint('Frame Transport: Error getting battery level: $e');
      return null;
    }
  }

  Future<String?> _getFromLoop(String key, {Duration timeout = const Duration(seconds: 5)}) async {
    int prefix = switch (key) {
      "loopStatus" => 0xE1,
      "micState" => 0xE2,
      "cameraState" => 0xE3,
      "frameLibHash" => 0xE4,
      _ => throw Exception("Invalid key: $key"),
    };

    final futureResult = _frame!.bluetooth.getDataWithPrefix(prefix).first.timeout(timeout);

    if (!await _sendUntilEchoed("GET $key", maxAttempts: 1, timeout: timeout)) {
      return null;
    }

    try {
      Uint8List result = await futureResult;
      debugPrint("Received $key from frame: ${utf8.decode(result)}");
      _isLooping = true;
      return utf8.decode(result);
    } on TimeoutException {
      debugPrint("Timeout occurred while getting $key from loop");
      return null;
    }
  }

  Future<void> _sendHeartbeat() async {
    debugPrint("Sending heartbeat to frame");
    final heartbeatBytes = Uint8List.fromList(utf8.encode("HEARTBEAT"));
    await _frame?.bluetooth.sendData(heartbeatBytes);
  }

  Future<bool> _sendUntilEchoed(String data,
      {int maxAttempts = 3, Duration timeout = const Duration(seconds: 10)}) async {
    if (_frame == null || !_frame!.isConnected) {
      return false;
    }

    Uint8List bytesToSend = Uint8List.fromList(utf8.encode(data));
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        var future = _frame!.bluetooth.stringResponse.firstWhere((element) => element == "ECHO:$data").timeout(timeout);
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
          if (e is BrilliantBluetoothException) {
            if (e.msg.contains("service not found")) {
              // Could trigger reconnection logic here
            }
          } else {
            debugPrint("Error sending $data to frame: $e");
            return false;
          }
        }
      }
    }
    return false;
  }

  Future<void> _setTimeOnFrame() async {
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

  @override
  Future<void> dispose() async {
    // Cancel subscriptions
    _heartbeatSubscription?.cancel();
    _debugSubscription?.cancel();

    // Close all stream controllers
    for (final controller in _streamControllers.values) {
      await controller.close();
    }
    _streamControllers.clear();

    await _connectionStateController.close();

    // Frame cleanup
    if (_frame != null) {
      _frame!.bluetooth.disconnect();
    }
    _frame = null;
  }
}
