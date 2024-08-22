import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/devices/deviceType.dart';
import 'package:friend_private/devices/friend/friendDevice.dart';
import 'package:friend_private/devices/friend/openGlassDeviceType.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/errors.dart';

class OpenGlassDevice extends FriendDevice {
  OpenGlassDevice(super.id);

  @override
  DeviceType get deviceType => OpenGlassDeviceType();

  @override
  Future<void> init() async {
    await super.init();
    try {
      final friendService = await getService(friendServiceUuid);
      if (friendService != null) {
        imageCaptureControlCharacteristic =
            await getCharacteristic(imageCaptureControlCharacteristicUuid);
        imageDataStreamCharacteristic =
            await getCharacteristic(imageDataStreamCharacteristicUuid);
      } else {
        logServiceNotFoundError('OpenGlass', id);
        print("Did not find friend service on OpenGlass");
      }
    } catch (e) {
      print('Error initializing openGlassDevice: $e');
    }
  }

  BluetoothCharacteristic? imageCaptureControlCharacteristic;
  BluetoothCharacteristic? imageDataStreamCharacteristic;

  @override
  Future<void> cameraStartPhotoController() async {
    imageCaptureControlCharacteristic = await ensureCharacteristicFilled(
        imageCaptureControlCharacteristic,
        imageCaptureControlCharacteristicUuid);

    if (imageCaptureControlCharacteristic == null) {
      logCharacteristicNotFoundError('Image capture control', id);
      return;
    }
    // Capture photo once every 10s
    await imageCaptureControlCharacteristic!.write([0x0A]);
    print("OpenGlassDevice cameraStartPhotoController started");
  }

  @override
  Future<void> cameraStopPhotoController() async {
    imageCaptureControlCharacteristic = await ensureCharacteristicFilled(
        imageCaptureControlCharacteristic,
        imageCaptureControlCharacteristicUuid);

    if (imageCaptureControlCharacteristic == null) {
      logCharacteristicNotFoundError('Image capture control', id);
      return;
    }

    await imageCaptureControlCharacteristic!.write([0x00]);
    print("OpenGlassDevice cameraStopPhotoController stopped");
  }

    Future<StreamSubscription?> _getImageBytesListener(
      {required void Function(List<int>) onImageBytesReceived}) async {
    imageDataStreamCharacteristic = await ensureCharacteristicFilled(
        imageDataStreamCharacteristic, imageDataStreamCharacteristicUuid);

    if (imageDataStreamCharacteristic == null) {
      logCharacteristicNotFoundError('Image data stream', id);
      return null;
    }

    try {
      await imageDataStreamCharacteristic!.setNotifyValue(true);
      print("OpenGlassDevice _getImageBytesListener subscribed");
    } catch (e, stackTrace) {
      logSubscribeError('Image data stream', id, e, stackTrace);
      return null;
    }

    debugPrint('Subscribed to imageBytes stream from Friend Device');
    var listener =
        imageDataStreamCharacteristic!.lastValueStream.listen((value) {
      if (value.isNotEmpty) onImageBytesReceived(value);
    });

    final device = BluetoothDevice.fromId(id);
    device.cancelWhenDisconnected(listener);

    return listener;
  }

  @override
  Future<bool> canPhotoStream() async {
    imageDataStreamCharacteristic = await ensureCharacteristicFilled(
        imageDataStreamCharacteristic, imageDataStreamCharacteristicUuid);

    if (imageDataStreamCharacteristic == null) {
      logCharacteristicNotFoundError('Image data stream', id);
      return false;
    }
    return true;
  }

  @override
  Future<StreamSubscription?> getImageListener(
      {required void Function(Uint8List base64JpgData) onImageReceived}) async {
    if (!await canPhotoStream()) {
      return null;
    }
    print("OpenGlassDevice getImageListener called");
    ImageBytesUtil imageBytesUtil = ImageBytesUtil();
    var bleBytesStream = await _getImageBytesListener(
      onImageBytesReceived: (List<int> value) async {
        if (value.isEmpty) return;
        Uint8List data = Uint8List.fromList(value);
        // print(data);
        Uint8List? completedImage = imageBytesUtil.processChunk(data);
        if (completedImage != null && completedImage.isNotEmpty) {
          debugPrint('Completed image bytes length: ${completedImage.length}');
          onImageReceived(completedImage);
        }
      },
    );
    bleBytesStream?.onDone(() {
      debugPrint('Image listener done');
      cameraStopPhotoController();
    });
    return bleBytesStream;
  }
}
