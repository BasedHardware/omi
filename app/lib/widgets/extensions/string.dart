import 'dart:convert';

extension StringExtensions on String {
  String get decodeSting {
    try {
      return utf8.decode(codeUnits);
    } on Exception catch (_) {
      return this;
    }
  }
}
