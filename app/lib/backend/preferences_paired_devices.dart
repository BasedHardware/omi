import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/logger.dart';

/// Saved-device slots for multi-device capture (an Omi pendant plus OmiGlass).
/// Each slot holds one small `BtDevice` record, never user history.
extension PairedDeviceSlots on SharedPreferencesUtil {
  /// Second device paired next to [SharedPreferencesUtil.btDevice] for
  /// multi-modal capture (an OmiGlass alongside an Omi pendant). Both slots are
  /// auto-connected; which one carries audio and which one carries photos is
  /// decided at runtime by `DevicePairingRoles`, not by the slot.
  BtDevice? get companionBtDevice {
    final String device = getString('companionBtDevice');
    if (device.isEmpty) return null;
    try {
      final decoded = BtDevice.fromJson(jsonDecode(device));
      return decoded.id.isEmpty ? null : decoded;
    } catch (e) {
      Logger.debug('Error decoding companion device: $e');
      return null;
    }
  }

  set companionBtDevice(BtDevice? value) {
    if (value == null || value.id.isEmpty) {
      remove('companionBtDevice');
      return;
    }
    saveString('companionBtDevice', jsonEncode(value.toJson()));
    final devices = btDevices;
    final index = devices.indexWhere((device) => device.id == value.id);
    if (index >= 0) {
      devices[index] = value;
    } else {
      devices.add(value);
    }
    saveStringList('btDevices', devices.map((device) => jsonEncode(device.toJson())).toList());
  }

  /// Ids of every saved device the app should keep connected.
  List<String> get pairedDeviceIds {
    final ids = <String>[];
    final primary = btDevice;
    if (primary.id.isNotEmpty) ids.add(primary.id);
    final companion = companionBtDevice;
    if (companion != null && !ids.contains(companion.id)) ids.add(companion.id);
    return ids;
  }

  /// Drops [deviceId] from every saved slot. When the primary slot is
  /// forgotten, the companion (if any) is promoted so the app keeps
  /// reconnecting to the device the user still owns.
  void forgetSavedBtDevice(String deviceId) {
    if (deviceId.isEmpty) return;
    final companion = companionBtDevice;
    if (companion?.id == deviceId) {
      remove('companionBtDevice');
    }
    if (btDevice.id == deviceId) {
      if (companion != null && companion.id != deviceId) {
        remove('companionBtDevice');
        saveString('btDevice', jsonEncode(companion.toJson()));
      } else {
        // Cleared by a write, not remove(): only a btDevice write emits
        // deviceChanges, which retires the saved-reconnect target.
        saveString('btDevice', '');
      }
    }
    final devices = btDevices.where((device) => device.id != deviceId).toList();
    saveStringList('btDevices', devices.map((device) => jsonEncode(device.toJson())).toList());
  }
}
