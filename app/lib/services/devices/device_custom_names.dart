import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

/// The names people give their devices, kept on this phone per device id, and which of them have
/// been synced with the name stored on the device.
extension DeviceCustomNames on SharedPreferencesUtil {
  set deviceCustomNames(Map<String, String> value) => saveString('deviceCustomNames', jsonEncode(value));

  Map<String, String> get deviceCustomNames {
    final encoded = getString('deviceCustomNames');
    if (encoded.isEmpty) return {};
    try {
      final decoded = jsonDecode(encoded) as Map<String, dynamic>;
      return decoded.map((key, value) => MapEntry(key, value.toString()));
    } catch (e) {
      Logger.debug('Error decoding device custom names: $e');
      return {};
    }
  }

  String? getDeviceCustomName(String deviceId) {
    if (deviceId.isEmpty) return null;
    final name = deviceCustomNames[deviceId]?.trim() ?? '';
    return name.isEmpty ? null : name;
  }

  Future<void> setDeviceCustomName(String deviceId, String name) async {
    if (deviceId.isEmpty) return;
    final names = deviceCustomNames;
    final trimmed = name.trim();
    if (trimmed.isEmpty) {
      names.remove(deviceId);
    } else {
      names[deviceId] = trimmed;
    }
    await saveString('deviceCustomNames', jsonEncode(names));
  }

  Future<void> clearDeviceCustomName(String deviceId) async {
    await setDeviceCustomName(deviceId, '');
    await clearDeviceNameSynced(deviceId);
  }

  Future<void> adoptStoredDeviceName(String deviceId, String? storedName) async {
    if (storedName == null) return;
    await setDeviceCustomName(deviceId, storedName);
    await markDeviceNameSynced(deviceId);
  }

  bool shouldPushLocalDeviceName(String deviceId, String storedName) =>
      storedName.isEmpty && getDeviceCustomName(deviceId) != null && !hasSyncedDeviceName(deviceId);

  List<String> get deviceNameSyncedIds => List<String>.from(getStringList('deviceNameSyncedIds'));

  bool hasSyncedDeviceName(String deviceId) => deviceNameSyncedIds.contains(deviceId);

  Future<void> markDeviceNameSynced(String deviceId) async {
    if (deviceId.isEmpty) return;
    final ids = deviceNameSyncedIds;
    if (ids.contains(deviceId)) return;
    ids.add(deviceId);
    await saveStringList('deviceNameSyncedIds', ids);
  }

  Future<void> clearDeviceNameSynced(String deviceId) async {
    final ids = deviceNameSyncedIds;
    if (!ids.remove(deviceId)) return;
    await saveStringList('deviceNameSyncedIds', ids);
  }
}
