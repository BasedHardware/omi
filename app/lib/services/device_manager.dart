import 'package:flutter/material.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

class DeviceManager extends ChangeNotifier {
  final Map<String, DeviceConnection> _devices = {};

  Map<String, DeviceConnection> get devices => Map.unmodifiable(_devices);
  int get count => _devices.length;

  // Connect multiple devices
  Future<void> connectAll(List<BTDevice> list) async {
    for (final device in list) {
      await connectOne(device);
    }
  }

  // Connect one device
  Future<void> connectOne(BTDevice device) async {
    if (_devices.containsKey(device.id)) return;
    
    final conn = DeviceConnectionFactory.create(device);
    if (conn == null) throw Exception('Device not supported');
    
    await conn.connect();
    _devices[device.id] = conn;
    notifyListeners();
  }

  // Disconnect device
  Future<void> disconnect(String id) async {
    final conn = _devices.remove(id);
    if (conn != null) {
      await conn.disconnect();
      notifyListeners();
    }
  }

  @override
  void dispose() {
    for (final conn in _devices.values) {
      conn.disconnect();
    }
    super.dispose();
  }
}
