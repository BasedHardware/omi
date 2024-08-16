import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:frame_sdk/display.dart';
import 'package:frame_sdk/frame_sdk.dart';
import '../../backend/schema/bt_device.dart';
import '../deviceType.dart';
import 'frameDeviceType.dart';
import 'frameLibrary.dart';

import '../btleDevice.dart';

class FrameDevice extends BtleDevice {
  final String _id;
  Frame? _frame;

  FrameDevice(this._id) : super();

  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _modelNumber;

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

  @override
  Future<void> afterConnect() async {
    if (_frame == null) {
      await init();
    }
    if (_frame == null || _frame!.isConnected == false) {
      return;
    }
    final libraryVersion =
        friendMicRecordAndSend.hashCode.toRadixString(35).substring(0, 6);
    final _ = await _frame!.bluetooth.sendString(
        "frame.file.mkdir(\"lib-$libraryVersion\");print(\"c\")",
        awaitResponse: true);
    await _frame!.injectLibraryFunction(
        "friendMicRecordAndSend", friendMicRecordAndSend, libraryVersion);
    await _frame!.files.deleteFile("main.lua");
    _frame!.display.showText("Listening...",
        color: PaletteColors.darkGreen, align: Alignment2D.middleCenter);
  }

  @override
  Future cameraStartPhotoController() {
    // TODO: implement cameraStartPhotoController
    throw UnimplementedError();
  }

  @override
  Future cameraStopPhotoController() {
    // TODO: implement cameraStopPhotoController
    throw UnimplementedError();
  }

  @override
  Future<BleAudioCodec> getAudioCodec() {
    return Future.value(BleAudioCodec.pcm8);
  }

  @override
  Future<StreamSubscription?> getAudioBytesListener(
      {required void Function(List<int>) onAudioBytesReceived}) async {
    if (_frame == null || _frame!.isConnected == false) {
      await init();
    }
    if (_frame == null || _frame!.isConnected == false) {
      return null;
    }
    await _frame!.runLua('frame.microphone.stop()', checked: true);

    StreamSubscription<Uint8List> subscription =
        _frame!.bluetooth.getDataWithPrefix(0xEE).listen((value) {
      if (value.isNotEmpty) onAudioBytesReceived(value);
    }, onDone: () async {
      await _frame?.bluetooth.sendBreakSignal();
      await _frame?.runLua('frame.microphone.stop()', checked: true);
    });
    final audioCodec = await getAudioCodec();
    await _frame!.runLua(
      'friendMicRecordAndSend(${audioCodec.sampleRate},${audioCodec.bitDepth},nil)',
    );

    debugPrint('Subscribed to audioBytes stream from Frame Device');

    final device = BluetoothDevice.fromId(id);
    device.cancelWhenDisconnected(subscription);

    if (Platform.isAndroid) await device.requestMtu(512);


    return subscription;
  }

  @override
  Future<StreamSubscription<List<int>>?> getBatteryLevelListener(
      {void Function(int)? onBatteryLevelChange}) async {
    if (_frame == null) {
      await init();
    }
    if (_frame == null || _frame!.isConnected == false) {
      return null;
    }

    int? lastBatteryLevel;
    Timer? batteryCheckTimer;

    Future<void> checkBatteryLevel() async {
      int currentLevel = await _frame!.getBatteryLevel();
      if (currentLevel != lastBatteryLevel) {
        lastBatteryLevel = currentLevel;
        onBatteryLevelChange?.call(currentLevel);
      }
    }

    // Initial battery level check
    await checkBatteryLevel();

    // Set up periodic battery level check
    batteryCheckTimer =
        Timer.periodic(const Duration(seconds: 60), (_) => checkBatteryLevel());

    StreamController<List<int>> controller = StreamController<List<int>>();
    StreamSubscription<List<int>> listener = controller.stream.listen((value) {
      if (value.isNotEmpty) {
        onBatteryLevelChange?.call(value[0]);
      }
    });

    // Cancel the timer when the stream is closed
    listener.onDone(() {
      batteryCheckTimer?.cancel();
    });

    return listener;
  }

  @override
  Future<StreamSubscription?> getImageBytesListener(
      {required void Function(List<int> p1) onImageBytesReceived}) {
    // TODO: implement getBleImageBytesListener
    throw UnimplementedError();
  }

  @override
  Future<bool> canPhotoStream() {
    return Future.value(false);
  }

  @override
  Future<void> init() async {
    _frame ??= Frame();
    if (await _frame!.connectToDevice(id)) {
      _firmwareRevision = await _frame!.evaluate("frame.FIRMWARE_VERSION");
      _hardwareRevision = "1";
      _modelNumber = "1";
    }
  }

  @override
  Future<int> retrieveBatteryLevel() async {
    if (_frame == null || _frame!.isConnected == false) {
      await init();
    }
    if (_frame == null || _frame!.isConnected == false) {
      return -1;
    }
    return await _frame!.getBatteryLevel();
  }

  @override
  DeviceType get deviceType => FrameDeviceType();
}
