import 'dart:convert';

import 'package:flutter/services.dart';

/// Caps a text field at [maxBytes] of UTF-8 instead of a character count, so a
/// name typed in the app always fits the device's byte-limited storage.
/// Input that would overflow is rejected rather than cut mid-character.
class Utf8ByteLimitFormatter extends TextInputFormatter {
  Utf8ByteLimitFormatter(this.maxBytes);

  final int maxBytes;

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    if (utf8.encode(newValue.text).length <= maxBytes) return newValue;
    return oldValue;
  }
}
