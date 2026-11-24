// Remembers, per pendant, a firmware release that uploaded but did not install.
//
// Some original CV1 pendants run a stock bootloader that rejects new application
// images: the upload completes, the pendant restarts and comes back on its old
// version with its data intact. Offering the same release again would repeat a
// slow upload that cannot succeed, so the app holds that release for that
// pendant and presents it as the newest firmware the device supports.
//
// The hold only suppresses repeat offers. It is not a safety boundary: losing it
// (reinstall, another phone) costs one more harmless attempt. A newer release is
// offered normally.
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class FirmwareUpdateHold {
  FirmwareUpdateHold(this._prefs);

  static const String storageKey = 'firmwareUpdateHoldsV1';

  /// Bound on remembered pendants; the oldest entries are dropped first.
  static const int maxEntries = 16;

  final SharedPreferences _prefs;

  static Future<FirmwareUpdateHold> load() async => FirmwareUpdateHold(await SharedPreferences.getInstance());

  Map<String, String> _read() {
    final raw = _prefs.getString(storageKey);
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return {};
      return {
        for (final entry in decoded.entries)
          if (entry.key is String && entry.value is String) entry.key as String: entry.value as String,
      };
    } on FormatException {
      return {};
    }
  }

  static String _normalize(String version) {
    final trimmed = version.trim();
    return trimmed.startsWith('v') ? trimmed.substring(1) : trimmed;
  }

  /// The held release for [deviceId], if any.
  String? heldVersion(String deviceId) => deviceId.isEmpty ? null : _read()[deviceId];

  /// Whether [version] is held for [deviceId]: the pendant already took it and kept its firmware.
  static Future<bool> heldFor(String deviceId, String version) async =>
      (await load()).isHeld(deviceId: deviceId, version: version);

  /// True when [version] is the release held for [deviceId].
  bool isHeld({required String deviceId, required String version}) {
    final held = heldVersion(deviceId);
    return held != null && version.trim().isNotEmpty && held == _normalize(version);
  }

  /// Records that [version] uploaded to [deviceId] but the pendant kept its old firmware.
  Future<void> hold({required String deviceId, required String version}) async {
    final normalized = _normalize(version);
    if (deviceId.isEmpty || normalized.isEmpty) return;
    final holds = _read()..remove(deviceId);
    holds[deviceId] = normalized;
    while (holds.length > maxEntries) {
      holds.remove(holds.keys.first);
    }
    await _prefs.setString(storageKey, jsonEncode(holds));
  }

  /// Forgets the hold for [deviceId], for example after a successful install.
  Future<void> clear(String deviceId) async {
    final holds = _read();
    if (holds.remove(deviceId) == null) return;
    await _prefs.setString(storageKey, jsonEncode(holds));
  }
}
