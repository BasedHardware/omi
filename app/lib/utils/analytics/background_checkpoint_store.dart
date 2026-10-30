import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'background_resource_telemetry.dart';

/// One bounded local lifecycle checkpoint. No audio, transcript or device ID.
class PreferencesBackgroundCheckpointStore implements BackgroundCheckpointStore {
  static const _key = 'mobile_background_observation_v1';
  @override
  Future<Map<String, Object>?> read() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(_key);
    if (value == null) return null;
    if (value.length > 2048) {
      await clear();
      return null;
    }
    try {
      return Map<String, Object>.from(jsonDecode(value) as Map);
    } catch (_) {
      await clear();
      return null;
    }
  }

  @override
  Future<void> write(Map<String, Object> checkpoint) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(checkpoint));
  }

  @override
  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key);
  }
}
