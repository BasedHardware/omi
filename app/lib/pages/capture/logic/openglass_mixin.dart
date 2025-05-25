import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/openai.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:tuple/tuple.dart';

mixin OpenGlassMixin {
  List<Tuple2<String, String>> photos = [];
  ImageBytesUtil imageBytesUtil = ImageBytesUtil();
  StreamSubscription? _bleBytesStream;

  // TODO: use connection directly
  Future<BleAudioCodec> getAudioCodec(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return BleAudioCodec.pcm8;
    return connection.getAudioCodec();
  }

  Future<StreamSubscription?> getImageListener({
    required void Function(Uint8List) onImageReceived,
    required String deviceId,
  }) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return null;
    return connection.getImageListener(onImageReceived: onImageReceived);
  }

  Future<void> cameraStopPhotoController(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;
    return connection.cameraStopPhotoController();
  }

  Future<void> cameraStartPhotoController(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;
    return connection.cameraStartPhotoController();
  }

  Future<bool> hasPhotoStreamingCharacteristic(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return false;
    return connection.hasPhotoStreamingCharacteristic();
  }

  Future<void> openGlassProcessing(
    BtDevice device,
    Function(List<Tuple2<String, String>>) onPhotosUpdated,
    Function(bool) setHasTranscripts,
  ) async {
    _bleBytesStream = await getImageListener(
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
      deviceId: device.id,
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
