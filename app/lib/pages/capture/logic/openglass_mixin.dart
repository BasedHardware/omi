import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/openai.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:tuple/tuple.dart';

mixin OpenGlassMixin {
  List<Tuple2<String, String>> photos = [];
  ImageBytesUtil imageBytesUtil = ImageBytesUtil();
  StreamSubscription? _bleBytesStream;

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.getAudioCodec() ?? Future.value(BleAudioCodec.pcm8);
  }

  Future<StreamSubscription?> _getImageListener(
    String deviceId, {
    required void Function(Uint8List base64JpgData) onImageReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.getImageListener(onImageReceived: onImageReceived) ?? Future.value(null);
  }

  Future _cameraStopPhotoController(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.cameraStopPhotoController() ?? Future.value(null);
  }

  Future _cameraStartPhotoController(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.cameraStartPhotoController() ?? Future.value(null);
  }

  Future<bool> _hasPhotoStreamingCharacteristic(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.hasPhotoStreamingCharacteristic() ?? Future.value(false);
  }

  Future<void> openGlassProcessing(
    BtDevice device,
    Function(List<Tuple2<String, String>>) onPhotosUpdated,
    Function(bool) setHasTranscripts,
  ) async {
    _bleBytesStream = await _getImageListener(
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
    await _cameraStopPhotoController(device.id);
    await _cameraStartPhotoController(device.id);
  }

  Future<bool> isGlassesDevice(String deviceId) async {
    return await _hasPhotoStreamingCharacteristic(deviceId);
  }

  void disposeOpenGlass() {
    _bleBytesStream?.cancel();
    photos.clear();
  }
}
