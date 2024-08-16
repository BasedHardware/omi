import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/openai.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:tuple/tuple.dart';

mixin OpenGlassMixin {
  List<Tuple2<String, String>> photos = [];
  ImageBytesUtil imageBytesUtil = ImageBytesUtil();
  StreamSubscription? _bleBytesStream;

  Future<void> openGlassProcessing(
    Device device,
    Function(List<Tuple2<String, String>>) onPhotosUpdated,
    Function(bool) setHasTranscripts,
  ) async {
    _bleBytesStream = await device.getBleImageBytesListener(
      onImageBytesReceived: (List<int> value) async {
        if (value.isEmpty) return;
        Uint8List data = Uint8List.fromList(value);
        // print(data);
        Uint8List? completedImage = imageBytesUtil.processChunk(data);
        if (completedImage != null && completedImage.isNotEmpty) {
          debugPrint('Completed image bytes length: ${completedImage.length}');
          getPhotoDescription(completedImage).then((description) {
            photos.add(Tuple2(base64Encode(completedImage), description));
            onPhotosUpdated(photos);
            debugPrint('photos: ${photos.length}');
            setHasTranscripts(true);
          });
        }
      },
    );
    await device.cameraStopPhotoController();
    await device.cameraStartPhotoController();
  }

  Future<bool> isGlassesDevice(Device device) async {
    return await device.hasPhotoStreamingCharacteristic();
  }

  void disposeOpenGlass() {
    _bleBytesStream?.cancel();
    photos.clear();
  }
}
