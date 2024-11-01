import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';

class DeviceWidget extends StatelessWidget {
  final BtDevice device;

  const DeviceWidget({
    super.key,
    required this.device,
  });

  @override
  Widget build(BuildContext context) {
    if (device.type == DeviceType.watch) {
      return Icon(Icons.watch);
    }
    return Icon(Icons.photo_library);
  }
}
