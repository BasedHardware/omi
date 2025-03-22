import 'dart:async';
import 'package:flutter/material.dart';
import 'package:friend_private/services/devices/device_connection.dart';
import 'package:friend_private/services/devices/models.dart';

/// A mock device connection implementation for web platforms
class WebMockDeviceConnection implements DeviceConnection {
  final String deviceId;
  bool _isConnected = false;
  Timer? _mockDataTimer;
  final StreamController<DeviceConnectionState> _stateController = 
      StreamController<DeviceConnectionState>.broadcast();
  final StreamController<DeviceData> _dataController = 
      StreamController<DeviceData>.broadcast();

  WebMockDeviceConnection({required this.deviceId}) {
    debugPrint('Created WebMockDeviceConnection for device: $deviceId');
  }

  @override
  Stream<DeviceConnectionState> get connectionState => _stateController.stream;

  @override
  Stream<DeviceData> get dataStream => _dataController.stream;

  @override
  Future<void> connect() async {
    if (_isConnected) return;
    
    debugPrint('WebMockDeviceConnection: Connecting to device $deviceId');
    
    // Simulate connection delay
    await Future.delayed(const Duration(milliseconds: 500));
    
    _isConnected = true;
    _stateController.add(DeviceConnectionState.connected);
    
    // Start sending mock data periodically
    _startMockDataStream();
    
    debugPrint('WebMockDeviceConnection: Connected to device $deviceId');
  }

  @override
  Future<void> disconnect() async {
    if (!_isConnected) return;
    
    debugPrint('WebMockDeviceConnection: Disconnecting from device $deviceId');
    
    _stopMockDataStream();
    
    _isConnected = false;
    _stateController.add(DeviceConnectionState.disconnected);
    
    debugPrint('WebMockDeviceConnection: Disconnected from device $deviceId');
  }

  @override
  Future<void> dispose() async {
    debugPrint('WebMockDeviceConnection: Disposing connection for device $deviceId');
    
    await disconnect();
    
    await _stateController.close();
    await _dataController.close();
  }

  @override
  Future<void> sendCommand(DeviceCommand command) async {
    if (!_isConnected) {
      debugPrint('WebMockDeviceConnection: Cannot send command, not connected');
      return;
    }
    
    debugPrint('WebMockDeviceConnection: Sending command to device $deviceId: ${command.type}');
    
    // Simulate command processing delay
    await Future.delayed(const Duration(milliseconds: 200));
    
    // Mock response based on command type
    switch (command.type) {
      case DeviceCommandType.startAudio:
        debugPrint('WebMockDeviceConnection: Started audio streaming (mock)');
        break;
      case DeviceCommandType.stopAudio:
        debugPrint('WebMockDeviceConnection: Stopped audio streaming (mock)');
        break;
      default:
        debugPrint('WebMockDeviceConnection: Processed command ${command.type} (mock)');
    }
  }

  void _startMockDataStream() {
    _mockDataTimer?.cancel();
    _mockDataTimer = Timer.periodic(const Duration(seconds: 2), (timer) {
      if (!_isConnected) {
        timer.cancel();
        return;
      }
      
      // Send mock device data
      final mockData = DeviceData(
        type: DeviceDataType.status,
        payload: {'battery': '85', 'firmware': '1.0.0', 'status': 'ok'},
      );
      
      _dataController.add(mockData);
    });
  }

  void _stopMockDataStream() {
    _mockDataTimer?.cancel();
    _mockDataTimer = null;
  }

  @override
  bool get isConnected => _isConnected;
}
