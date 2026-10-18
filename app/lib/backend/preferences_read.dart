part of 'preferences.dart';

// Native codecs decode arrays without preserving Dart generic arguments.
// Validate their elements before normalizing a string-list preference.
bool _isStringList(Object value) => value is List && value.every((element) => element is String);

extension _PreferencesRead on SharedPreferencesUtil {
  T _readOrDefault<T>(String key, T fallback) {
    final value = SharedPreferencesUtil._preferences?.get(key);
    if (value == null) return fallback;
    if (fallback is List<String> && _isStringList(value)) {
      return List<String>.from(value as List) as T;
    }
    if (value is T) return value as T;
    if (!PhysicalQualification.enabled) {
      unawaited(SharedPreferencesUtil._quarantine(key, value, reason: 'type_mismatch'));
    }
    return fallback;
  }
}
