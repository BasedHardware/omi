part of 'capture_controller.dart';

/// Camera streaming for the device session: the companion OmiGlass paired next
/// to the recording pendant, or the recording device itself when it has a
/// camera. Photos ride on the audio session's `/v4/listen` socket.
extension _CapturePhotoStreaming on CaptureController {
  /// Applies a new companion camera device. Returns false when nothing changed.
  Future<bool> _applyPhotoDevice(BtDevice? device) async {
    final companion = device != null && device.id != _recordingDevice?.id ? device : null;
    final changed = companion?.id != _companionPhotoDevice?.id;
    _companionPhotoDevice = companion;
    if (!changed) return false;
    Logger.debug('companion photo device changed to ${companion?.id}');

    if (_photoStreamDeviceId != null && _photoStreamDeviceId != photoDevice?.id) {
      await _stopDevicePhotoStreaming();
    }
    final sessionActive = _recordingDevice != null &&
        (recordingState == RecordingState.deviceRecord || recordingState == RecordingState.pause);
    if (sessionActive) {
      await _initiateDevicePhotoStreaming();
    }
    return true;
  }

  /// Opens the camera stream. Returns false when there is nothing to stream.
  Future<bool> _openDevicePhotoStream() async {
    // Photos ride on the audio session's socket, so a camera without a
    // recording device has nowhere to send them.
    final device = photoDevice;
    if (device == null || _recordingDevice == null) return false;
    if (_blePhotoStream != null && _photoStreamDeviceId == device.id) return false;
    final connection = await _ensureDeviceConnection(device.id);
    if (connection == null || !await connection.hasPhotoStreamingCharacteristic()) return false;

    await _blePhotoStream?.cancel();
    _blePhotoStream = null;
    final generation = ++_photoStreamGeneration;
    _photoStreamDeviceId = device.id;
    await connection.performCameraStartPhotoController();
    _blePhotoStream = lifetime.takeSubscription(
      _blePhotoStream,
      await connection.performGetImageListener(
        onImageReceived: (orientedImage) async {
          if (generation != _photoStreamGeneration) return;
          final rotatedImageBytes = rotateImage(orientedImage);
          final String tempId = 'temp_img_${DateTime.now().millisecondsSinceEpoch}';
          final String base64Image = base64Encode(rotatedImageBytes);

          // Add placeholder to UI for immediate feedback
          photos.add(ConversationPhoto(id: tempId, base64: base64Image, createdAt: DateTime.now()));
          photos = List.from(photos);
          _segmentsPhotosVersion++;
          _publishCaptureChange();
          await emitBase64ImageChunks(
            base64Image,
            id: tempId,
            emit: (payload) async {
              if (generation != _photoStreamGeneration) return;
              if (_socket?.state == SocketServiceState.connected) {
                _socket?.send(payload);
              }
            },
          );
        },
      ),
    );
    if (_blePhotoStream == null) {
      await _stopDevicePhotoStreaming();
    }
    return true;
  }

  /// Cancels the photo listener and tells the camera device to stop capturing.
  Future<void> _stopDevicePhotoStreaming() async {
    await _blePhotoStream?.cancel();
    _blePhotoStream = null;
    _photoStreamGeneration++;
    final deviceId = _photoStreamDeviceId;
    _photoStreamDeviceId = null;
    if (deviceId == null) return;
    final connection = await _ensureDeviceConnection(deviceId);
    if (connection != null && await connection.hasPhotoStreamingCharacteristic()) {
      await connection.performCameraStopPhotoController();
    }
  }
}
