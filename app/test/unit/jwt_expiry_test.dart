import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/jwt_expiry.dart';

String _token(Map<String, dynamic> payload) {
  String segment(Map<String, dynamic> value) => base64Url.encode(utf8.encode(jsonEncode(value))).replaceAll('=', '');
  return '${segment({'alg': 'RS256'})}.${segment(payload)}.signature';
}

void main() {
  test('reads exp out of the token', () {
    final expiry = DateTime.utc(2026, 8, 16, 12, 0, 0);

    final result = jwtExpiry(_token({'exp': expiry.millisecondsSinceEpoch ~/ 1000}));

    expect(result?.toUtc(), expiry);
  });

  test('an expired token reports a past expiry', () {
    final past = DateTime.now().toUtc().subtract(const Duration(days: 3));

    final result = jwtExpiry(_token({'exp': past.millisecondsSinceEpoch ~/ 1000}));

    expect(result!.isBefore(DateTime.now()), isTrue);
  });

  test('returns null for anything it cannot read, so the caller keeps its fallback', () {
    expect(jwtExpiry(''), isNull);
    expect(jwtExpiry('not-a-jwt'), isNull);
    expect(jwtExpiry('header.%%%.signature'), isNull);
    expect(jwtExpiry(_token({'sub': 'user-1'})), isNull);
    expect(jwtExpiry(_token({'exp': 'soon'})), isNull);
    expect(jwtExpiry(_token({'exp': 0})), isNull);
  });

  test('tolerates base64 padding the encoder omitted', () {
    // Firebase strips '=' padding; base64Url.decode rejects that without normalize.
    final token = _token({'exp': 1786900104, 'sub': 'padding-sensitive'});

    expect(token.split('.')[1].contains('='), isFalse);
    expect(jwtExpiry(token), isNotNull);
  });
}
