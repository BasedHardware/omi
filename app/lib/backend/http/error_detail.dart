import 'dart:convert';

import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;

/// Human-readable reason out of a FastAPI error body, or null when the body
/// carries none.
///
/// ``detail`` is deliberately untyped on the wire: most endpoints answer with a
/// plain string, but some answer with a map, such as the phone-call quota error
/// (see ``check_call_access`` in ``backend/utils/phone_calls.py``). Reading it as
/// a string crashes on that map, so both shapes are handled here once. A list
/// (request validation errors) carries no reason a person can act on.
String? errorDetailMessage(String body) {
  try {
    final parsed = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(body) as Map<String, dynamic>);
    final detail = parsed.detail;
    if (detail is String) {
      return detail.trim().isEmpty ? null : detail;
    }
    if (detail is Map) {
      final code = detail['error'];
      if (code == 'phone_call_quota_exceeded') {
        final limit = detail['monthly_limit'];
        return limit is int
            ? 'Monthly call limit reached ($limit calls). It resets at the start of next month.'
            : 'Monthly call limit reached. It resets at the start of next month.';
      }
      if (code is String && code.trim().isNotEmpty) {
        return code;
      }
    }
  } catch (_) {}
  return null;
}
