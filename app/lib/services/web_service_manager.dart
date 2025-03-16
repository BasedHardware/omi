import 'package:flutter/material.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/sockets.dart';
import 'package:friend_private/services/wals.dart';

/// Web-compatible service manager that doesn't use dart:isolate
class WebServiceManager {
  late IDeviceService _device;
  late ISocketService _socket;
  late IWalService _wal;

  static WebServiceManager? _instance;

  static WebServiceManager _create() {
    WebServiceManager sm = WebServiceManager();
    sm._device = DeviceService();
    sm._socket = SocketServicePool();
    sm._wal = WalService();

    return sm;
  }

  static WebServiceManager instance() {
    if (_instance == null) {
      throw Exception("Web service manager is not initiated");
    }

    return _instance!;
  }

  IDeviceService get device => _device;
  ISocketService get socket => _socket;
  IWalService get wal => _wal;

  static void init() {
    if (_instance != null) {
      throw Exception("Web service manager is already initiated");
    }
    _instance = WebServiceManager._create();
    debugPrint('WebServiceManager initialized successfully');
  }

  Future<void> start() async {
    _device.start();
    _wal.start();
  }

  void deinit() async {
    await _wal.stop();
    _device.stop();
  }
}
