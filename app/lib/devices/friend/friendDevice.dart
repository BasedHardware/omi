import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/BtServiceDef.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/devices/deviceType.dart';
import 'package:friend_private/devices/friend/friendDeviceType.dart';
import 'package:friend_private/utils/ble/errors.dart';
import '../btleDevice.dart';

const BtServiceDef friendServiceUuid =
    BtServiceDef('19b10000-e8f2-537e-4f6c-d104768a1214', 'Friend Service');
const BtCharacteristicDef imageCaptureControlCharacteristicUuid =
    BtCharacteristicDef('19b10006-e8f2-537e-4f6c-d104768a1214',
        'Image Capture Control', friendServiceUuid);
const BtCharacteristicDef imageDataStreamCharacteristicUuid =
    BtCharacteristicDef('19b10005-e8f2-537e-4f6c-d104768a1214',
        'Image Data Stream', friendServiceUuid);
const BtCharacteristicDef audioDataStreamCharacteristicUuid =
    BtCharacteristicDef('19b10001-e8f2-537e-4f6c-d104768a1214',
        'Audio Data Stream', friendServiceUuid);
const BtCharacteristicDef audioCodecCharacteristicUuid = BtCharacteristicDef(
    '19b10002-e8f2-537e-4f6c-d104768a1214', 'Audio Codec', friendServiceUuid);

const BtServiceDef batteryServiceUuid =
    BtServiceDef('0000180f-0000-1000-8000-00805f9b34fb', 'Battery Service');
const BtCharacteristicDef batteryLevelCharacteristicUuid = BtCharacteristicDef(
    '00002a19-0000-1000-8000-00805f9b34fb',
    'Battery Level',
    batteryServiceUuid);

const BtServiceDef deviceInformationServiceUuid =
    BtServiceDef('0000180a-0000-1000-8000-00805f9b34fb', 'Device Information');
const BtCharacteristicDef modelNumberCharacteristicUuid = BtCharacteristicDef(
    '00002a24-0000-1000-8000-00805f9b34fb',
    'Model Number',
    deviceInformationServiceUuid);
const BtCharacteristicDef firmwareRevisionCharacteristicUuid =
    BtCharacteristicDef('00002a26-0000-1000-8000-00805f9b34fb',
        'Firmware Revision', deviceInformationServiceUuid);
const BtCharacteristicDef hardwareRevisionCharacteristicUuid =
    BtCharacteristicDef('00002a27-0000-1000-8000-00805f9b34fb',
        'Hardware Revision', deviceInformationServiceUuid);
const BtCharacteristicDef manufacturerNameCharacteristicUuid =
    BtCharacteristicDef('00002a29-0000-1000-8000-00805f9b34fb',
        'Manufacturer Name', deviceInformationServiceUuid);

class FriendDevice extends BtleDevice {
  final String _id;

  FriendDevice(this._id) : super();

  @override
  DeviceType get deviceType => FriendDeviceType();

  Future<void> init() async {
    try {
      final deviceInfoService = await getService(deviceInformationServiceUuid);
      if (deviceInfoService != null) {
        _modelNumber = await readCharacteristic(modelNumberCharacteristicUuid);
        _firmwareRevision =
            await readCharacteristic(firmwareRevisionCharacteristicUuid);
        _hardwareRevision =
            await readCharacteristic(hardwareRevisionCharacteristicUuid);
      } else {
        logServiceNotFoundError('Device information', id);
        _modelNumber = 'Friend';
        _firmwareRevision = '1.0.2';
        _hardwareRevision = 'Seeed Xiao BLE Sense';
        print("Did not find device information service, assuming old firmware");
      }

      final friendService = await getService(friendServiceUuid);
      if (friendService != null) {
        audioDataStreamCharacteristic =
            await getCharacteristic(audioDataStreamCharacteristicUuid);
        audioCodecCharacteristic =
            await getCharacteristic(audioCodecCharacteristicUuid);
      } else {
        logServiceNotFoundError('Friend', id);
        print("Did not find friend service");
      }

      final batteryService = await getService(batteryServiceUuid);
      if (batteryService != null) {
        batteryLevelCharacteristic =
            await getCharacteristic(batteryLevelCharacteristicUuid);
      } else {
        logServiceNotFoundError('Battery', id);
        print("Did not find battery level characteristic");
      }
    } catch (e) {
      print('Error initializing FriendDevice: $e');
    }
  }

  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _modelNumber;

  @override
  String get firmwareRevision {
    if (_firmwareRevision == null) {
      init();
    }
    return _firmwareRevision!;
  }

  @override
  String get hardwareRevision {
    if (_hardwareRevision == null) {
      init();
    }
    return _hardwareRevision!;
  }

  @override
  String get id => _id;

  @override
  String get manufacturerName => deviceType.manufacturerName;

  @override
  String get modelNumber {
    if (_modelNumber == null) {
      init();
    }
    return _modelNumber!;
  }

  BluetoothCharacteristic? audioDataStreamCharacteristic;
  BluetoothCharacteristic? audioCodecCharacteristic;
  BluetoothCharacteristic? batteryLevelCharacteristic;
  BluetoothCharacteristic? deviceInformationCharacteristic;
  BluetoothCharacteristic? modelNumberCharacteristic;
  BluetoothCharacteristic? firmwareRevisionCharacteristic;
  BluetoothCharacteristic? hardwareRevisionCharacteristic;
  BluetoothCharacteristic? manufacturerNameCharacteristic;

  @override
  Future<void> cameraStartPhotoController() async {
    throw UnimplementedError();
  }

  @override
  Future<void> cameraStopPhotoController() async {
    throw UnimplementedError();
  }

  @override
  Future<BleAudioCodec> getAudioCodec() async {
    audioCodecCharacteristic = await ensureCharacteristicFilled(
        audioCodecCharacteristic, audioCodecCharacteristicUuid);

    if (audioCodecCharacteristic == null) {
      logCharacteristicNotFoundError('Audio codec', id);
      return BleAudioCodec.pcm8;
    }

    var codecId = 1;
    BleAudioCodec codec = BleAudioCodec.pcm8;

    var codecValue = await audioCodecCharacteristic!.read();
    if (codecValue.isNotEmpty) {
      codecId = codecValue[0];
    }

    switch (codecId) {
      case 1:
        codec = BleAudioCodec.pcm8;
        break;
      case 20:
        codec = BleAudioCodec.opus;
        break;
      default:
        logErrorMessage('Unknown codec id: $codecId', id);
    }

    return codec;
  }

  @override
  Future<StreamSubscription?> getAudioBytesListener(
      {required void Function(List<int>) onAudioBytesReceived}) async {
    audioDataStreamCharacteristic = await ensureCharacteristicFilled(
        audioDataStreamCharacteristic, audioDataStreamCharacteristicUuid);

    if (audioDataStreamCharacteristic == null) {
      logCharacteristicNotFoundError('Audio data stream', id);
      return null;
    }
    try {
      await audioDataStreamCharacteristic!.setNotifyValue(true);
    } catch (e, stackTrace) {
      logSubscribeError('Audio data stream', id, e, stackTrace);
      return null;
    }

    debugPrint('Subscribed to audioBytes stream from Friend Device');
    var listener =
        audioDataStreamCharacteristic!.lastValueStream.listen((value) {
      if (value.isNotEmpty) onAudioBytesReceived(value);
    });

    final device = BluetoothDevice.fromId(id);
    device.cancelWhenDisconnected(listener);

    if (Platform.isAndroid) await device.requestMtu(512);

    return listener;
  }

  @override
  Future<StreamSubscription<List<int>>?> getBatteryLevelListener(
      {void Function(int)? onBatteryLevelChange}) async {
    batteryLevelCharacteristic = await ensureCharacteristicFilled(
        batteryLevelCharacteristic, batteryLevelCharacteristicUuid);

    var currValue = await batteryLevelCharacteristic!.read();
    if (currValue.isNotEmpty) {
      debugPrint('Battery level: ${currValue[0]}');
      onBatteryLevelChange?.call(currValue[0]);
    }

    try {
      await batteryLevelCharacteristic!.setNotifyValue(true);
    } catch (e, stackTrace) {
      logSubscribeError('Battery level', id, e, stackTrace);
      return null;
    }

    var listener = batteryLevelCharacteristic!.lastValueStream.listen((value) {
      if (value.isNotEmpty) {
        onBatteryLevelChange?.call(value[0]);
      }
    });

    return listener;
  }

  Future<StreamSubscription?> _getImageBytesListener(
      {required void Function(List<int>) onImageBytesReceived}) async {
    return null;
  }

  @override
  Future<bool> canPhotoStream() async {
    return false;
  }

  @override
  Future<int> retrieveBatteryLevel() async {
    batteryLevelCharacteristic = await ensureCharacteristicFilled(
        batteryLevelCharacteristic, batteryLevelCharacteristicUuid);

    if (batteryLevelCharacteristic == null) {
      logCharacteristicNotFoundError('Battery level', id);
      return -1;
    }

    var currValue = await batteryLevelCharacteristic!.read();
    if (currValue.isNotEmpty) return currValue[0];
    return -1;
  }

  @override
  Future<void> afterConnect() async {}

  @override
  Future<StreamSubscription?> getImageListener(
      {required void Function(Uint8List base64JpgData) onImageReceived}) async {
        print("called getImageListener on a Friend device, which does not support photo streaming");
    return null;
  }
}
