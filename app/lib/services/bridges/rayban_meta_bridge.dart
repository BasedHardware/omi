import 'dart:typed_data';

import 'package:omi/gen/pigeon_communicator.g.dart';

/// Public bridge that implements Pigeon callbacks and forwards them to Dart-side listeners.
class RayBanMetaFlutterBridge implements RayBanMetaFlutterAPI {
  final void Function(String state)? onRegistrationStateChangedCb;
  final void Function(RayBanMetaGlasses glasses)? onGlassesDiscoveredCb;
  final void Function(String deviceId, String state)? onConnectionStateChangedCb;
  final void Function(Uint8List pcm16Frame, double sampleRate)? onAudioFrameCb;
  final void Function(bool glassesRouteActive)? onAudioRouteChangedCb;
  final void Function(Uint8List jpegBytes, int orientationDegrees)? onPhotoCapturedCb;
  final void Function(String state)? onCameraStateChangedCb;
  final void Function(String status)? onCameraPermissionChangedCb;
  final void Function(String code, String message)? onErrorCb;

  RayBanMetaFlutterBridge({
    this.onRegistrationStateChangedCb,
    this.onGlassesDiscoveredCb,
    this.onConnectionStateChangedCb,
    this.onAudioFrameCb,
    this.onAudioRouteChangedCb,
    this.onPhotoCapturedCb,
    this.onCameraStateChangedCb,
    this.onCameraPermissionChangedCb,
    this.onErrorCb,
  });

  @override
  void onRegistrationStateChanged(String state) {
    onRegistrationStateChangedCb?.call(state);
  }

  @override
  void onGlassesDiscovered(RayBanMetaGlasses glasses) {
    onGlassesDiscoveredCb?.call(glasses);
  }

  @override
  void onConnectionStateChanged(String deviceId, String state) {
    onConnectionStateChangedCb?.call(deviceId, state);
  }

  @override
  void onAudioFrame(Uint8List pcm16Frame, double sampleRate) {
    onAudioFrameCb?.call(pcm16Frame, sampleRate);
  }

  @override
  void onAudioRouteChanged(bool glassesRouteActive) {
    onAudioRouteChangedCb?.call(glassesRouteActive);
  }

  @override
  void onPhotoCaptured(Uint8List jpegBytes, int orientationDegrees) {
    onPhotoCapturedCb?.call(jpegBytes, orientationDegrees);
  }

  @override
  void onCameraStateChanged(String state) {
    onCameraStateChangedCb?.call(state);
  }

  @override
  void onCameraPermissionChanged(String status) {
    onCameraPermissionChangedCb?.call(status);
  }

  @override
  void onError(String code, String message) {
    onErrorCb?.call(code, message);
  }
}
