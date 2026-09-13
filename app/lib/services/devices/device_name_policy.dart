import 'dart:convert';

/// Why a proposed device name was rejected.
enum DeviceNameError { empty, tooLong, invalidCharacters }

/// Client-side mirror of the firmware rules for the BLE device-name
/// characteristic (`omi/firmware/omi/src/lib/core/device_name.h`).
///
/// The firmware is the authority and rejects anything outside these rules;
/// mirroring them here lets the UI explain a problem before a BLE round trip.
class OmiDeviceNamePolicy {
  OmiDeviceNamePolicy._();

  /// Maximum UTF-8 byte length accepted by the firmware. Fits a single ATT
  /// Write Request at the default 23-byte MTU and the 31-byte scan response.
  static const int maxBytes = 20;

  /// Trims surrounding whitespace; the firmware rejects names that start or
  /// end with a space, so the UI never sends what the user did not mean.
  static String normalize(String raw) => raw.trim();

  /// Returns null when [name] (already normalized) is acceptable.
  static DeviceNameError? validate(String name) {
    if (name.isEmpty) return DeviceNameError.empty;
    for (final rune in name.runes) {
      if (rune < 0x20 || rune == 0x7F) return DeviceNameError.invalidCharacters;
      // Unpaired surrogates cannot be encoded as UTF-8.
      if (rune >= 0xD800 && rune <= 0xDFFF) return DeviceNameError.invalidCharacters;
    }
    if (utf8.encode(name).length > maxBytes) return DeviceNameError.tooLong;
    return null;
  }

  /// UTF-8 bytes to write to the characteristic. Throws [ArgumentError] when
  /// [name] does not pass [validate].
  static List<int> encode(String name) {
    final error = validate(name);
    if (error != null) {
      throw ArgumentError.value(name, 'name', 'invalid device name: $error');
    }
    return utf8.encode(name);
  }

  /// Decodes a characteristic read. Returns null for an empty payload or one
  /// the firmware would never have produced (malformed UTF-8).
  static String? decode(List<int> bytes) {
    if (bytes.isEmpty) return null;
    try {
      final name = utf8.decode(bytes, allowMalformed: false);
      return validate(name) == null ? name : null;
    } on FormatException {
      return null;
    }
  }
}
