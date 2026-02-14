import 'dart:typed_data';

import 'package:omi/gen/flutter_communicator.g.dart';

/// Public bridge that implements Pigeon callbacks and forwards them to Dart-side listeners.
class AppleWatchFlutterBridge implements WatchRecorderFlutterAPI {
  final void Function(Uint8List bytes, int chunkIndex, bool isLast, double sampleRate)? onChunk;
  final void Function()? onRecordingStartedCb;
  final void Function()? onRecordingStoppedCb;
  final void Function(String error)? onRecordingErrorCb;
  final void Function(bool granted)? onMicPermissionCb;
  final void Function(bool granted)? onMainAppMicPermissionCb;
  final void Function(double batteryLevel, int batteryState)? onBatteryUpdateCb;
  final void Function()? onDeviceRecordingRequestedCb;

  AppleWatchFlutterBridge({
    this.onChunk,
    this.onRecordingStartedCb,
    this.onRecordingStoppedCb,
    this.onRecordingErrorCb,
    this.onMicPermissionCb,
    this.onMainAppMicPermissionCb,
    this.onBatteryUpdateCb,
    this.onDeviceRecordingRequestedCb,
  });

  @override
  void onAudioData(Uint8List audioData) {}

  @override
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate) {
    onChunk?.call(audioChunk, chunkIndex, isLast, sampleRate);
  }

  @override
  void onRecordingStarted() {
    onRecordingStartedCb?.call();
  }

  @override
  void onRecordingStopped() {
    onRecordingStoppedCb?.call();
  }

  @override
  void onRecordingError(String error) {
    onRecordingErrorCb?.call(error);
  }

  @override
  void onMicrophonePermissionResult(bool granted) {
    onMicPermissionCb?.call(granted);
  }

  @override
  void onMainAppMicrophonePermissionResult(bool granted) {
    onMainAppMicPermissionCb?.call(granted);
  }

  @override
  void onWatchBatteryUpdate(double batteryLevel, int batteryState) {
    onBatteryUpdateCb?.call(batteryLevel, batteryState);
  }

  @override
  void onDeviceRecordingRequested() {
    onDeviceRecordingRequestedCb?.call();
  }
}
