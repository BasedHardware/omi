import 'dart:convert';

extension StringExtensions on String {
  /// Attempts to fix double-encoded UTF-8 strings.
  /// Only applies decoding if the string appears to be double-encoded
  /// (UTF-8 bytes incorrectly stored as Latin-1 characters).
  String get decodeString {
    // Quick check: if no high-byte characters that look like UTF-8 leading bytes,
    // the string is probably already correctly encoded
    if (!_looksDoubleEncoded()) {
      return this;
    }
    try {
      // Use latin1.encode to get byte values (treats each char as a byte),
      // then decode those bytes as UTF-8
      return utf8.decode(latin1.encode(this));
    } on Exception catch (_) {
      return this;
    }
  }

  /// Checks if the string appears to be double-encoded UTF-8.
  /// Double-encoding happens when UTF-8 bytes are incorrectly interpreted as Latin-1,
  /// resulting in patterns like "Ã©" instead of "é", or "â€"" instead of "—".
  bool _looksDoubleEncoded() {
    // Common UTF-8 leading byte patterns when misinterpreted as Latin-1:
    // - Ã (0xC3) followed by another character = 2-byte UTF-8 sequence
    // - â (0xE2) often starts 3-byte sequences (em-dash, curly quotes, etc.)
    // These patterns are very unlikely in correctly-encoded text
    for (int i = 0; i < length; i++) {
      final code = codeUnitAt(i);
      // Check for Latin-1 supplement range that looks like UTF-8 leading bytes
      if (code >= 0xC0 && code <= 0xF4) {
        // This could be a UTF-8 leading byte stored as Latin-1
        return true;
      }
    }
    return false;
  }

  String capitalize() {
    return isNotEmpty ? '${this[0].toUpperCase()}${substring(1)}' : '';
  }
}
