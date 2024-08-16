import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/deviceType.dart';

Future<List<Device>> bleFindDevices() {
  return AnyDeviceType().findDevices();
}
