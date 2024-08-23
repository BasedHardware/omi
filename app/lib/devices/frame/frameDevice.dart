import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:frame_sdk/bluetooth.dart';
import 'package:frame_sdk/frame_sdk.dart';
import '../../backend/schema/bt_device.dart';
import '../deviceType.dart';
import 'frameDeviceType.dart';
//import 'package:image/image.dart';

import '../btleDevice.dart';

const String _photoHeader =
    "/9j/4AAQSkZJRgABAgAAZABkAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/2wBDASIkJDAqMF40NF7GhHCExsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsb/wAARCAIAAgADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwA=";

class FrameDevice extends BtleDevice {
  final String _id;
  Frame? _frame;

  FrameDevice(this._id) : super();

  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _modelNumber;
  int? _batteryLevel;

  StreamSubscription? _heartbeatSubscription;

  @override
  String get firmwareRevision {
    return _firmwareRevision ?? 'Unknown';
  }

  @override
  String get hardwareRevision {
    return _hardwareRevision ?? 'Unknown';
  }

  @override
  String get id => _id;

  @override
  String get manufacturerName => deviceType.manufacturerName;

  @override
  String get modelNumber {
    return _modelNumber ?? 'Unknown';
  }

  Future<void> sendHeartbeat() async {
    print("Sending heartbeat to frame");
    final heartbeatBytes = Uint8List.fromList(utf8.encode("HEARTBEAT"));
    await _frame?.bluetooth.sendData(heartbeatBytes);
  }

  @override
  Future<void> afterConnect() async {
    if (_frame == null) {
      throw Exception("Frame is not initialised");
    }
    if (_frame!.isConnected == false) {
      return;
    }
    var debugSubscription = _frame!.bluetooth.stringResponse.listen((data) {
      print("Frame printed: $data");
    });
    bool isLoaded = false;
    bool isRunning = false;
    final String mainLuaContent =
        (await rootBundle.loadString('assets/device_assets/frameLib.lua'))
            .replaceAll("\t", "")
            .replaceAll("\n\n", "\n");
    final int friendLibHash = mainLuaContent.hashCode;

    try {
      isLoaded =
          await _frame!.evaluate("friendLibHash") == friendLibHash.toString();
      isRunning = await _frame!.evaluate("loopStatus == 1") == "true";
    } catch (e) {
      print('Error evaluating loopStatus: $e');
    }
    if (!isLoaded) {
      print(
          "About to send main.lua to frame, length = ${mainLuaContent.length}");
      try {
        await _frame!.files
            .writeFile("main.lua", utf8.encode(mainLuaContent), checked: true);
        print("Sent main.lua to frame");
        await _frame!.runLua("friendLibHash = $friendLibHash", checked: true);
      } catch (e) {
        print("Error sending main.lua to frame: $e");
      }
      await _frame!.runLua("require('main')");
      await _frame!.runLua("start()");
    } else if (!isRunning) {
      print("Frame already loaded, running start()");
      await _frame!.runLua("start()");
    } else {
      print("Frame loop already running");
    }
    await Future.delayed(const Duration(milliseconds: 1000));

    // Set up heartbeat timer and stream
    final heartbeatStream = Stream.periodic(const Duration(seconds: 5));
    _heartbeatSubscription = heartbeatStream.listen((_) {
      sendHeartbeat();
    });

    // Cancel heartbeat subscription when device disconnects
    device ??= BluetoothDevice.fromId(id);
    device!.cancelWhenDisconnected(_heartbeatSubscription!);
    device!.cancelWhenDisconnected(debugSubscription);
  }

  Future<bool> sendUntilEchoed(String data,
      {int maxAttempts = 3,
      Duration timeout = const Duration(seconds: 10)}) async {
    Uint8List bytesToSend = Uint8List.fromList(utf8.encode(data));
    //print("Sending $data to frame");

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        var future = _frame!.bluetooth.stringResponse
            .firstWhere((element) => element == "ECHO:$data")
            .timeout(timeout);
        await _frame!.bluetooth.sendData(bytesToSend);
        await future;
        //print("Received ECHO:$data from frame");
        return true;
      } catch (e) {
        if (e is TimeoutException) {
          print(
              "Timeout occurred while waiting for echo of $data. Attempt $attempt of $maxAttempts");
          if (attempt == maxAttempts) {
            print(
                "Failed to receive echo for $data after $maxAttempts attempts");
            await disconnectDevice();
            return false;
          }
        } else {
          print("Error sending $data to frame: $e");
          return false;
        }
      }
    }
    return false;
  }

  @override
  Future cameraStartPhotoController() async {
    await sendUntilEchoed("CAMERA START");
  }

  @override
  Future cameraStopPhotoController() async {
    await sendUntilEchoed("CAMERA STOP");
  }

  @override
  Future<BleAudioCodec> getAudioCodec() {
    return Future.value(BleAudioCodec.pcm8);
  }

  @override
  Future<StreamSubscription?> getAudioBytesListener(
      {required void Function(List<int>) onAudioBytesReceived}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await Future.doWhile(() async {
        await Future.delayed(Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }

    StreamSubscription<Uint8List> subscription =
        _frame!.bluetooth.getDataWithPrefix(0xEE).listen((value) {
      if (value.isNotEmpty) onAudioBytesReceived(value);
    }, onDone: () async {
      await sendUntilEchoed("MIC STOP");
    });

    device ??= BluetoothDevice.fromId(id);
    device!.cancelWhenDisconnected(subscription);

    final audioCodec = await getAudioCodec();
    await sendUntilEchoed("sampleRate=${audioCodec.sampleRate}");
    await Future.delayed(const Duration(milliseconds: 50));
    await sendUntilEchoed("bitDepth=${audioCodec.bitDepth}");
    await Future.delayed(const Duration(milliseconds: 50));
    if (!await sendUntilEchoed("MIC START")) {
      subscription.cancel();
      return null;
    }

    debugPrint('Subscribed to audioBytes stream from Frame Device');

    return subscription;
  }

  @override
  Future<StreamSubscription<List<int>>?> getBatteryLevelListener(
      {void Function(int)? onBatteryLevelChange}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await Future.doWhile(() async {
        await Future.delayed(Duration(milliseconds: 100));
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

    StreamSubscription<Uint8List> subscription =
        _frame!.bluetooth.getDataWithPrefix(0xCC).listen((value) {
      if (value.isNotEmpty) checkBatteryLevel(value);
    });

    device ??= BluetoothDevice.fromId(id);
    device!.cancelWhenDisconnected(subscription);

    return subscription;
  }

  @override
  Future<bool> canPhotoStream() {
    return Future.value(true);
  }

  @override
  Future<void> init() async {
    bool wasConnected = _frame?.isConnected ?? false;
    print("Initialising Frame Device");
    _frame ??= Frame();
    _frame!.useLibrary = false;
    device ??= BluetoothDevice.fromId(id);
    bool connected = false;
    if (device!.isConnected) {
      print("Device is already connected, so attaching to existing connection");
      connected = await _frame!.connectToExistingBleDevice(device!);
    } else {
      print("Device is not connected, so connecting to device");
      connected = await _frame!.connectToDevice(id);
    }
    if (connected) {
      _firmwareRevision = await _frame!.evaluate("frame.FIRMWARE_VERSION");
      _hardwareRevision = "1";
      _modelNumber = "1";

      if (Platform.isAndroid) {
        await device!.requestMtu(512);
      }

      
      await afterConnect();
      
    }
  }

  void dispose() {
    _heartbeatSubscription?.cancel();
    if (_frame != null) {
      _frame!.bluetooth.disconnect();
    }
  }

  @override
  Future<int> retrieveBatteryLevel() async {
    if (_frame == null || _frame!.isConnected == false) {
      await Future.doWhile(() async {
        await Future.delayed(Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }
    return _batteryLevel ?? -1;
  }

  @override
  DeviceType get deviceType => FrameDeviceType();

  @override
  Future<StreamSubscription?> getImageListener(
      {required void Function(Uint8List p1) onImageReceived}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await Future.doWhile(() async {
        await Future.delayed(Duration(milliseconds: 100));
        return !(_frame?.isConnected ?? false);
      });
    }

    StreamSubscription<Uint8List> subscription = _frame!.bluetooth
        .getDataOfType(FrameDataTypePrefixes.photoData)
        .listen((value) {
      if (value.isNotEmpty) {
        print("Received photo data from frame, length = ${value.length}");
        final header = base64.decode(_photoHeader);
        final combinedData = Uint8List.fromList([...header, ...value]);
        print(
            "Processed photo data from frame, length = ${combinedData.length}");
        onImageReceived(combinedData);
      }
    });
    subscription.onDone(() async {
      // await sendUntilEchoed("CAMERA STOP");
    });

    device!.cancelWhenDisconnected(subscription);

    return subscription;
  }
  /*
  THIS DOESN'T WORK :-(
  Uint8List _processPhoto(Uint8List imageBuffer) {
    ExifData exif = decodeJpgExif(imageBuffer) ?? ExifData();

    exif.exifIfd.make = "Brilliant Labs";
    exif.exifIfd.model = "Frame";
    exif.exifIfd.software = "Friend";
    exif.imageIfd.data[0x9207] = IfdValueShort(2);


    exif.imageIfd.data[0x9003] =
        IfdValueAscii(DateTime.now().toIso8601String());

    // Set orientation to rotate 90 degrees clockwise
    exif.imageIfd.orientation = 6;

    // Inject updated EXIF data back into the image
    final updatedImageBuffer = injectJpgExif(imageBuffer, exif);
    if (updatedImageBuffer == null) {
      throw Exception("Failed to inject EXIF data");
    }
    return updatedImageBuffer;
  }
  */
}
