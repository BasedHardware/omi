import 'dart:convert';

extension StringExtensions on String {
  String get decodeString {
    try {
      return utf8.decode(codeUnits);
    } on Exception catch (_) {
      return this;
    }
  }

  String capitalize() {
    return isNotEmpty ? '${this[0].toUpperCase()}${substring(1)}' : '';
  }
}
