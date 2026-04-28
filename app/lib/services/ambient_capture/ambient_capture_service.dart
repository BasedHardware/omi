import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';

import 'package:omi/services/ambient_capture/ambient_capture_health.dart';
import 'package:omi/services/ambient_capture/ambient_capture_models.dart';

class AmbientCaptureService {
  static const MethodChannel _control = MethodChannel('omi/ambient_capture/control');
  static const MethodChannel _policy = MethodChannel('omi/ambient_capture/policy');
  static const EventChannel _audio = EventChannel('omi/ambient_capture/audio');
  static const EventChannel _health = EventChannel('omi/ambient_capture/health');
  static const EventChannel _telemetry = EventChannel('omi/ambient_capture/telemetry');

  Stream<Uint8List>? _audioStream;
  Stream<AmbientCaptureHealth>? _healthStream;
  Stream<AmbientCaptureTelemetryEvent>? _telemetryStream;

  bool get isSupported => Platform.isAndroid;

  Stream<Uint8List> get audioStream {
    _audioStream ??= _audio.receiveBroadcastStream().map((event) => event as Uint8List);
    return _audioStream!;
  }

  Stream<AmbientCaptureHealth> get healthStream {
    _healthStream ??= _health.receiveBroadcastStream().map(
          (event) => AmbientCaptureHealth.fromJson(event as Map<dynamic, dynamic>),
        );
    return _healthStream!;
  }

  Stream<AmbientCaptureTelemetryEvent> get telemetryStream {
    _telemetryStream ??= _telemetry.receiveBroadcastStream().map(
          (event) => AmbientCaptureTelemetryEvent.fromJson(event as Map<dynamic, dynamic>),
        );
    return _telemetryStream!;
  }

  Future<bool> start() async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('start') ?? false;
  }

  Future<bool> stop() async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('stop') ?? false;
  }

  Future<bool> pause() async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('pause') ?? false;
  }

  Future<bool> resume() async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('resume') ?? false;
  }

  Future<bool> privateMode({bool enabled = true}) async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('privateMode', {'enabled': enabled}) ?? false;
  }

  Future<Map<dynamic, dynamic>> getStatus() async {
    if (!isSupported) return {};
    return await _control.invokeMethod<Map<dynamic, dynamic>>('getStatus') ?? {};
  }

  Future<AmbientCaptureHealth> getHealthState() async {
    if (!isSupported) {
      return AmbientCaptureHealth(state: AmbientCaptureHealthState.policyDisabled, timestamp: DateTime.now());
    }
    final json = await _control.invokeMethod<Map<dynamic, dynamic>>('getHealthState') ?? {};
    return AmbientCaptureHealth.fromJson(json);
  }

  Future<void> setFlutterState({bool? socketConnected, bool? networkAvailable, int? walQueueDepth}) async {
    if (!isSupported) return;
    await _control.invokeMethod('setFlutterState', {
      if (socketConnected != null) 'socketConnected': socketConnected,
      if (networkAvailable != null) 'networkAvailable': networkAvailable,
      if (walQueueDepth != null) 'walQueueDepth': walQueueDepth,
    });
  }

  Future<void> setPolicyConfig({
    String? activePluginId,
    String? publicKey,
    String? keyId,
    String? policyUrl,
    String? userId,
    String? deviceId,
    bool? revoked,
  }) async {
    if (!isSupported) return;
    await _control.invokeMethod('setPolicyConfig', {
      if (activePluginId != null) 'activePluginId': activePluginId,
      if (publicKey != null) 'publicKey': publicKey,
      if (keyId != null) 'keyId': keyId,
      if (policyUrl != null) 'policyUrl': policyUrl,
      if (userId != null) 'userId': userId,
      if (deviceId != null) 'deviceId': deviceId,
      if (revoked != null) 'revoked': revoked,
    });
  }

  Future<List<AmbientSpoolFile>> listSpoolFiles() async {
    if (!isSupported) return [];
    final files = await _control.invokeMethod<List<dynamic>>('listSpoolFiles') ?? [];
    return files.map((file) => AmbientSpoolFile.fromJson(file as Map<dynamic, dynamic>)).toList();
  }

  Future<Map<dynamic, dynamic>> getSpoolStats() async {
    if (!isSupported) return {};
    return await _control.invokeMethod<Map<dynamic, dynamic>>('getSpoolStats') ?? {};
  }

  Future<void> markSpoolFiles(List<String> paths, String status) async {
    if (!isSupported) return;
    await _control.invokeMethod('markSpoolFiles', {'paths': paths, 'status': status});
  }

  Future<void> deleteSpoolFiles({String? status}) async {
    if (!isSupported) return;
    await _control.invokeMethod('deleteSpoolFiles', {'status': status});
  }

  Future<bool> isAccessibilityEnabled() async {
    if (!isSupported) return false;
    return await _control.invokeMethod<bool>('isAccessibilityEnabled') ?? false;
  }

  Future<void> openAccessibilitySettings() async {
    if (!isSupported) return;
    await _control.invokeMethod('openAccessibilitySettings');
  }

  Future<Map<dynamic, dynamic>> verifyNativePolicy({
    required String payload,
    required String signature,
    required String publicKey,
  }) async {
    if (!isSupported) return {'accepted': false, 'reason': 'android_only'};
    return await _policy.invokeMethod<Map<dynamic, dynamic>>('verifyPolicy', {
          'payload': payload,
          'signature': signature,
          'publicKey': publicKey,
        }) ??
        {'accepted': false, 'reason': 'native_no_response'};
  }
}
