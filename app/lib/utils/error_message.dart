import 'dart:convert';

import 'package:flutter/services.dart' show PlatformException;

/// Reduces a caught error to one short line fit for a snackbar.
///
/// Call sites interpolate this into an `{error}` placeholder. Passing
/// `e.toString()` there puts `Exception:` prefixes, raw JSON response bodies and
/// `PlatformException(...)` dumps in front of the user; the sentence inside them
/// is what they can act on.
String readableError(Object? error, {int maxLength = 160}) {
  final text = _unwrap(error).trim();
  if (text.length <= maxLength) return text;
  return '${text.substring(0, maxLength - 1).trimRight()}…';
}

String _unwrap(Object? error) {
  if (error == null) return '';
  if (error is PlatformException) {
    final message = error.message?.trim();
    return (message != null && message.isNotEmpty) ? message : error.code;
  }
  final text = error.toString().trim().replaceFirst(RegExp(r'^_?\w*(Exception|Error):\s*'), '');
  return _detailFromJson(text) ?? text;
}

String? _detailFromJson(String text) {
  final start = text.indexOf('{');
  final end = text.lastIndexOf('}');
  if (start == -1 || end <= start) return null;
  try {
    final decoded = jsonDecode(text.substring(start, end + 1));
    if (decoded is Map) {
      for (final key in const ['detail', 'message', 'error']) {
        final value = decoded[key];
        if (value is String && value.trim().isNotEmpty) return value.trim();
      }
    }
  } catch (_) {}
  return null;
}
