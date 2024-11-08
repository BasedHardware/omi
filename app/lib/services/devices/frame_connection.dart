import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:frame_sdk/bluetooth.dart';
import 'package:frame_sdk/frame_sdk.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/devices/device_connection.dart';

const String _photoHeader =
    "/9j/4AAQSkZJRgABAgAAZABkAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/2wBDASIkJDAqMF40NF7GhHCExsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsb/wAARCAIAAgADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwA=";

class FrameDeviceConnection extends DeviceConnection {
  FrameDeviceConnection(super.device, super.bleDevice);

  get deviceId => device.id;

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await init();
  }

  // Mimic @app/lib/utils/ble/frame_communication.dart
  Frame? _frame;
  late String name;

  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _modelNumber;
  int? _batteryLevel;
  bool? _isLooping;

  StreamSubscription? _heartbeatSubscription;
  StreamSubscription<String>? _debugSubscription;

  String get firmwareRevision {
    return _firmwareRevision ?? 'Unknown';
  }

  String get hardwareRevision {
    return _hardwareRevision ?? 'Unknown';
  }

  String get manufacturerName => "Brilliant Labs";

  String get modelNumber {
    return _modelNumber ?? 'Unknown';
  }

  Stream<BluetoothConnectionState> get connectionStateStream {
    return bleDevice.connectionState;
  }

  @override
  Future<bool> isConnected() async {
    return connectionState == DeviceConnectionState.connected;
  }

  Future<void> sendHeartbeat() async {
    debugPrint("Sending heartbeat to frame");
    final heartbeatBytes = Uint8List.fromList(utf8.encode("HEARTBEAT"));
    await _frame?.bluetooth.sendData(heartbeatBytes);
  }

  Future<String?> getFromLoop(String key, {Duration timeout = const Duration(seconds: 5)}) async {
    int prefix = switch (key) {
      "loopStatus" => 0xE1,
      "micState" => 0xE2,
      "cameraState" => 0xE3,
      "frameLibHash" => 0xE4,
      _ => throw Exception("Invalid key: $key"),
    };

    final futureResult = _frame!.bluetooth.getDataWithPrefix(prefix).first.timeout(timeout);

    if (!await sendUntilEchoed("GET $key", maxAttempts: 1, timeout: timeout)) {
      return null;
    }

    try {
      Uint8List result = await futureResult;
      print("Received $key from frame: ${utf8.decode(result)}");
      _isLooping = true;
      return utf8.decode(result);
    } on TimeoutException {
      print("Timeout occurred while getting $key from loop");
      return null;
    }
  }

  Future<void> setTimeOnFrame() async {
    if (_isLooping == true) {
      String utcUnixEpochTime = (DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000).toString();
      String timeZoneOffset = DateTime.now().timeZoneOffset.inMinutes > 0 ? '+' : '-';
      timeZoneOffset +=
          '${DateTime.now().timeZoneOffset.inHours.abs().toString().padLeft(2, '0')}:${(DateTime.now().timeZoneOffset.inMinutes.abs() % 60).toString().padLeft(2, '0')}';
      await sendUntilEchoed("timeUtc=$utcUnixEpochTime");
      await sendUntilEchoed("timeZone=$timeZoneOffset");
    } else if (_isLooping == false) {
      _frame!.setTimeOnFrame(checked: false);
    }
  }

  Future<void> afterConnect() async {
    if (_frame == null) {
      throw Exception("Frame is not initialised");
    }
    if (_frame!.isConnected == false) {
      debugPrint("Frame is not connected in afterConnect!");
      return;
    }
    if (_debugSubscription != null) {
      _debugSubscription!.cancel();
    }
    _debugSubscription = _frame!.bluetooth.stringResponse.listen((data) {
      debugPrint("Frame printed: $data");
    });
    await setTimeOnFrame();
    bool isLoaded = false;
    bool isRunning = false;
    final String mainLuaContent = (await rootBundle.loadString('assets/device_assets/frame_lib.lua'))
        .replaceAll("\t", "")
        .replaceAll("\n\n", "\n");
    final int frameLibHash = mainLuaContent.hashCode;

    if (_isLooping == false) {
      final deviceframeLibHash = await _frame!.evaluate("frameLibHash");
      isLoaded = deviceframeLibHash == frameLibHash.toString();
      isRunning = false;
      debugPrint(
          "A deviceframeLibHash: $deviceframeLibHash, frameLibHash: $frameLibHash, isLoaded: $isLoaded, isRunning: $isRunning");
    } else if (_isLooping == true) {
      final deviceframeLibHash = await getFromLoop("frameLibHash");
      if (deviceframeLibHash == null) {
        isLoaded = false;
        isRunning = false;
      } else {
        isLoaded = deviceframeLibHash == frameLibHash.toString();
        isRunning = await getFromLoop("loopStatus") == "1";
      }
      print(
          "B deviceframeLibHash: $deviceframeLibHash, frameLibHash: $frameLibHash, isLoaded: $isLoaded, isRunning: $isRunning");
    } else {
      var deviceframeLibHash = await getFromLoop("frameLibHash");
      if (deviceframeLibHash == null) {
        deviceframeLibHash = await _frame!.evaluate("frameLibHash");
        if (deviceframeLibHash is int) {
          deviceframeLibHash = deviceframeLibHash.toString();
          _isLooping = false;
          isRunning = false;
        }
      } else {
        _isLooping = true;
        isRunning = await getFromLoop("loopStatus") == "1";
      }
      isLoaded = deviceframeLibHash == frameLibHash.toString();
      print(
          "C deviceframeLibHash: $deviceframeLibHash, frameLibHash: $frameLibHash, isLoaded: $isLoaded, isRunning: $isRunning");
    }

    if (isRunning && isLoaded) {
      await sendHeartbeat();
      await sendUntilEchoed("MIC START");
      await sendUntilEchoed("CAMERA START");
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

      await setTimeOnFrame();
    } else if (isLoaded && !isRunning) {
      await _frame!.bluetooth.sendBreakSignal();
      debugPrint("Frame already loaded, running start()");
      await setTimeOnFrame();
      await _frame!.runLua("start()");
    }
    await Future.delayed(const Duration(milliseconds: 1000));

    // Set up heartbeat timer and stream
    final heartbeatStream = Stream.periodic(const Duration(seconds: 5));
    _heartbeatSubscription = heartbeatStream.listen((_) {
      sendHeartbeat();
    });

    // Cancel heartbeat subscription when device disconnects
    var device = bleDevice;
    device!.cancelWhenDisconnected(_heartbeatSubscription!);
    device!.cancelWhenDisconnected(_debugSubscription!);
  }

  Future<bool> sendUntilEchoed(String data,
      {int maxAttempts = 3, Duration timeout = const Duration(seconds: 10)}) async {
    Uint8List bytesToSend = Uint8List.fromList(utf8.encode(data));
    //print("Sending $data to frame");
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        var future = _frame!.bluetooth.stringResponse.firstWhere((element) => element == "ECHO:$data").timeout(timeout);
        await _frame!.bluetooth.sendData(bytesToSend);
        await future;
        //print("Received ECHO:$data from frame");
        return true;
      } catch (e) {
        if (e is TimeoutException) {
          debugPrint("Timeout occurred while waiting for echo of $data. Attempt $attempt of $maxAttempts");
          if (attempt == maxAttempts) {
            debugPrint("Failed to receive echo for $data after $maxAttempts attempts");
            //await disconnectDevice();
            return false;
          }
        } else {
          if (e is BrilliantBluetoothException) {
            if (e.msg.contains("service not found")) {
              await init();
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

  Future disconnectDevice() async {
    var device = bleDevice;
    try {
      await device!.disconnect(queue: false);
    } catch (e) {
      print('bleDisconnectDevice failed: $e');
    }
  }

  @override
  Future<void> performCameraStartPhotoController() async {
    await sendUntilEchoed("CAMERA START");
  }

  @override
  Future<void> performCameraStopPhotoController() async {
    await sendUntilEchoed("CAMERA STOP");
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() {
    return Future.value(BleAudioCodec.pcm8);
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener(
      {required void Function(List<int>) onAudioBytesReceived}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await init();
      await Future.doWhile(() async {
        await Future.delayed(const Duration(milliseconds: 250));
        return !(_frame?.isConnected ?? false);
      });
    }

    StreamSubscription<Uint8List> subscription = _frame!.bluetooth.getDataWithPrefix(0xEE).listen((value) {
      _isLooping = true;
      if (value.isNotEmpty) onAudioBytesReceived(value);
    }, onDone: () async {
      await sendUntilEchoed("MIC STOP");
    });

    var device = bleDevice;
    device!.cancelWhenDisconnected(subscription);

    final audioCodec = await getAudioCodec();
    await sendUntilEchoed("sampleRate=${mapCodecToSampleRate(audioCodec)}");
    await Future.delayed(const Duration(milliseconds: 50));
    await sendUntilEchoed("bitDepth=${mapCodecToBitDepth(audioCodec)}");
    await Future.delayed(const Duration(milliseconds: 50));
    if (!await sendUntilEchoed("MIC START")) {
      subscription.cancel();
      return null;
    }

    debugPrint('Subscribed to audioBytes stream from Frame Device');

    return subscription;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener(
      {void Function(int)? onBatteryLevelChange}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await init();
      await Future.doWhile(() async {
        await Future.delayed(const Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }

    Future<void> checkBatteryLevel(Uint8List data) async {
      int currentLevel = data[0];
      if (currentLevel != _batteryLevel) {
        _batteryLevel = currentLevel;
        onBatteryLevelChange?.call(currentLevel);
      }
    }

    StreamSubscription<Uint8List> subscription = _frame!.bluetooth.getDataWithPrefix(0xCC).listen((value) {
      _isLooping = true;
      if (value.isNotEmpty) checkBatteryLevel(value);
    });

    var device = bleDevice;
    device!.cancelWhenDisconnected(subscription);

    return subscription;
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() {
    return Future.value(true);
  }

  Future<void> init() async {
    print("Initialising Frame Device");
    var device = bleDevice;
    if (_frame != null && device != null && _frame!.isConnected && device!.isConnected) {
      print("Device is already connected in init...?");
      //await afterConnect();
      //return;
    }
    _frame ??= Frame();
    _frame!.useLibrary = false;
    bool connected = false;
    if (device!.isConnected) {
      print("Device is already connected, so attaching to existing connection");
      connected = await _frame!.connectToExistingBleDevice(device!);
    } else {
      print("Device is not connected, so connecting to device");
      connected = await _frame!.connectToDevice(deviceId);
    }
    if (connected) {
      if (_isLooping == null || _isLooping == false) {
        Future.microtask(() async {
          try {
            _firmwareRevision = await _frame!.evaluate("frame.FIRMWARE_VERSION");
            _isLooping = false;
          } catch (e) {
            // Ignore error
          }
          try {
            _batteryLevel = int.parse(await _frame!.evaluate("frame.battery_level()"));
            _isLooping = false;
          } catch (e) {
            // Ignore error
          }
        });
      }
      await afterConnect();
    } else {
      print("Failed to connect to Frame Device");
    }
  }

  void dispose() {
    _heartbeatSubscription?.cancel();
    if (_frame != null) {
      _frame!.bluetooth.disconnect();
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    if (_frame == null || _frame!.isConnected == false) {
      await init();
      await Future.doWhile(() async {
        await Future.delayed(const Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }
    return _batteryLevel ?? -1;
  }

  @override
  Future<StreamSubscription?> performGetImageListener({required void Function(Uint8List p1) onImageReceived}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await Future.doWhile(() async {
        await Future.delayed(const Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }

    StreamSubscription<Uint8List> subscription =
        _frame!.bluetooth.getDataOfType(FrameDataTypePrefixes.photoData).listen((value) {
      if (value.isNotEmpty) {
        debugPrint("Received photo data from frame, length = ${value.length}");
        final header = base64.decode(_photoHeader);
        final combinedData = Uint8List.fromList([...header, ...value]);
        debugPrint("Processed photo data from frame, length = ${combinedData.length}");
        onImageReceived(combinedData);
      }
    });
    subscription.onDone(() async {
      // await sendUntilEchoed("CAMERA STOP");
    });

    var device = bleDevice;
    device!.cancelWhenDisconnected(subscription);

    return subscription;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    // not yet implemented
    return null;
  }

  @override
  Future<List<int>> performGetStorageList() {
    return Future.value(<int>[]);
  }

  // @override
  //  Future<List<int>> performGetStorageList() {

  //   return <int>[];
  //  }
  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) {
    return Future.value(null);
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) {
    return Future.value(false);
  }
}
