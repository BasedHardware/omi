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

  Future<void> refreshOpenGlassCamera(String deviceId) async {
    // Stop current capture
    await cameraStopPhotoController(deviceId);
    
    // Wait briefly for camera to stop
    await Future.delayed(Duration(milliseconds: 500));
    
    // Clear any cached images
    photos.clear();
    
    // Start camera with single capture command to trigger immediate photo
    await cameraStartPhotoController(deviceId);
    
    // Wait briefly then send a single photo command to force immediate capture
    await Future.delayed(Duration(milliseconds: 200));
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection != null) {
      try {
        // Send single photo command (-1 = immediate single capture)
        await connection.performCameraStartPhotoController();
      } catch (e) {
        debugPrint('Error sending immediate capture command: $e');
      }
    }
  }

  Future<void> openGlassProcessing(
    BtDevice device,
    Function(List<Tuple2<String, String>>) onPhotosUpdated,
    Function(bool) setHasTranscripts,
  ) async {
    _bleBytesStream = await getImageListener(
      onImageReceived: (Uint8List completedImage) async {
        if (completedImage.isNotEmpty) {
          Tuple2<String, String> photo = Tuple2(base64Encode(completedImage), '');
          photos.add(photo);
          getPhotoDescription(completedImage).then((description) {
            if (photos.contains(photo)) {
              int index = photos.indexOf(photo);
              photos[index] = Tuple2(photo.item1, description);
            onPhotosUpdated(photos);
            setHasTranscripts(true);
            }
          });
          onPhotosUpdated(photos);
        }
      },
      deviceId: device.id,
    );
    
    // Initial camera setup
    await cameraStopPhotoController(device.id);
    await Future.delayed(Duration(milliseconds: 300));
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
