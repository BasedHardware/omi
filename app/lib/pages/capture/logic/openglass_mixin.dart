import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/openai.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:tuple/tuple.dart';

mixin OpenGlassMixin {
  List<Tuple2<String, String>> photos = [];
  ImageBytesUtil imageBytesUtil = ImageBytesUtil();
  StreamSubscription? _bleBytesStream;

  Future<void> openGlassProcessing(
    BTDeviceStruct device,
    Function(List<Tuple2<String, String>>) onPhotosUpdated,
    Function(bool) setHasTranscripts,
  ) async {
    _bleBytesStream = await getImageListener(
      device.id,
      onImageReceived: (Uint8List completedImage) async {
        if (completedImage.isNotEmpty) {
          debugPrint('Completed image bytes length: ${completedImage.length}');
          Tuple2<String, String> photo = Tuple2(base64Encode(completedImage), '');
          photos.add(photo);
          getPhotoDescription(completedImage).then((description) {
            photos[photos.indexOf(photo)] = Tuple2(photo.item1, description);
            onPhotosUpdated(photos);
            debugPrint('photos: ${photos.length}');
            setHasTranscripts(true);
          });
        }
      },
    );
    await cameraStopPhotoController(device.id);
    await cameraStartPhotoController(device.id);
  }

  Future<bool> isGlassesDevice(String deviceId) async {
    return await hasPhotoStreamingCharacteristic(deviceId);
  }

  void disposeOpenGlass() {
    _bleBytesStream?.cancel();
    photos.clear();
  }
}
