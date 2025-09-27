import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/services/devices/communication/device_communicator.dart';

class AppleWatchCommunicator extends DeviceCommunicator {
  final WatchRecorderHostAPI _hostAPI = WatchRecorderHostAPI();
  final StreamController<Map<String, dynamic>> _messageController;
  final StreamController<DeviceConnectionState> _connectionStateController;

  AppleWatchCommunicator()
      : _messageController = StreamController<Map<String, dynamic>>.broadcast(),
        _connectionStateController = StreamController<DeviceConnectionState>.broadcast();

  @override
  String get deviceId => 'apple-watch';

  @override
  DeviceConnectionState get connectionState => DeviceConnectionState.disconnected;

  @override
  Stream<DeviceConnectionState> get connectionStateStream => _connectionStateController.stream;

  @override
  Future<void> connect() async {
    final supported = await _hostAPI.isWatchSessionSupported();
    final paired = await _hostAPI.isWatchPaired();
    final reachable = await _hostAPI.isWatchReachable();

    if (!supported) {
      throw Exception('Apple Watch session not supported on this device');
    }
    if (!paired) {
      throw Exception('Apple Watch not paired');
    }

    if (reachable) {
      _connectionStateController.add(DeviceConnectionState.connected);
    } else {
      _connectionStateController.add(DeviceConnectionState.disconnected);
    }
  }

  @override
  Future<void> disconnect() async {
    _connectionStateController.add(DeviceConnectionState.disconnected);
  }

  @override
  Future<bool> isConnected() async {
    final supported = await _hostAPI.isWatchSessionSupported();
    if (!supported) return false;
    final paired = await _hostAPI.isWatchPaired();
    if (!paired) return false;
    final reachable = await _hostAPI.isWatchReachable();
    return reachable;
  }

  @override
  Future<Map<String, dynamic>?> sendCommand(String command, [Map<String, dynamic>? params]) async {
    switch (command) {
      case 'getBattery':
        return await _getBatteryLevel();
      case 'getAudioCodec':
        return {'codec': 'pcm16'}; // Apple Watch always uses 16kHz PCM
      case 'startRecording':
        return await _startRecording();
      case 'stopRecording':
        return await _stopRecording();
      case 'getWatchInfo':
        return await _getWatchInfo();
      case 'checkPermission':
        return await _checkPermission();
      case 'requestPermission':
        return await _requestPermission();
      case 'getBatteryState':
        return await _getBatteryState();
      default:
        return null;
    }
  }

  @override
  Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

  @override
  Future<void> dispose() async {
    await _messageController.close();
    await _connectionStateController.close();
  }

  // Apple Watch-specific methods
  Future<Map<String, dynamic>> _getBatteryLevel() async {
    try {
      final batteryLevel = await _hostAPI.getWatchBatteryLevel();
      return {'level': batteryLevel.round()};
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery level: $e');
      return {'level': -1};
    }
  }

  Future<Map<String, dynamic>> _startRecording() async {
    try {
      await _hostAPI.startRecording();
      return {'success': true};
    } catch (e) {
      debugPrint('Apple Watch: Error starting recording: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _stopRecording() async {
    try {
      await _hostAPI.stopRecording();
      return {'success': true};
    } catch (e) {
      debugPrint('Apple Watch: Error stopping recording: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _getWatchInfo() async {
    try {
      final deviceInfo = await _hostAPI.getWatchInfo();
      return {'info': deviceInfo};
    } catch (e) {
      debugPrint('Apple Watch: Error getting device info: $e');
      return {'info': {}};
    }
  }

  Future<Map<String, dynamic>> _checkPermission() async {
    try {
      final hasPermission = await _hostAPI.checkMainAppMicrophonePermission();
      return {'hasPermission': hasPermission};
    } catch (e) {
      debugPrint('Apple Watch: Error checking permission: $e');
      return {'hasPermission': false};
    }
  }

  Future<Map<String, dynamic>> _requestPermission() async {
    try {
      await _hostAPI.requestMainAppMicrophonePermission();
      return {'success': true};
    } catch (e) {
      debugPrint('Apple Watch: Error requesting permission: $e');
      return {'success': false, 'error': e.toString()};
    }
  }

  Future<Map<String, dynamic>> _getBatteryState() async {
    try {
      final batteryState = await _hostAPI.getWatchBatteryState();
      return {'state': batteryState};
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery state: $e');
      return {'state': 0};
    }
  }
}
