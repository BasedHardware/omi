import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';

const kPermissionStateToBool = {
  PermissionStatus.granted: true,
  PermissionStatus.limited: true,
  PermissionStatus.denied: false,
  PermissionStatus.restricted: false,
  PermissionStatus.permanentlyDenied: false,
};

const microphonePermission = Permission.microphone;
const notificationsPermission = Permission.notification;

Future<bool> getPermissionStatus(Permission setting) async {
  if (kIsWeb) {
    return true;
  }
  final status = await setting.status;
  return kPermissionStateToBool[status]!;
}

Future<void> requestPermission(Permission setting) async {
  if (kIsWeb) {
    return;
  }
  await setting.request();
}
