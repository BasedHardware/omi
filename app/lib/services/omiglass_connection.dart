import 'dart:async';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_connection.dart';

class OmiGlassConnection extends DeviceConnection {
  OmiGlassConnection(super.device, super.transport);

  @override
  Future<void> connect() async {
    await tran
