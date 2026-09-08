import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/phone_calls.dart';

void main() {
  group('errorDetailMessage', () {
    test('returns a string detail as-is', () {
      final body = jsonEncode({'detail': 'No verified phone number found. Verify a number first.'});
      expect(errorDetailMessage(body), 'No verified phone number found. Verify a number first.');
    });

    test('returns null for a blank string detail', () {
      expect(errorDetailMessage(jsonEncode({'detail': '   '})), isNull);
    });

    test('renders the quota map instead of throwing on it', () {
      final body = jsonEncode({
        'detail': {
          'error': 'phone_call_quota_exceeded',
          'monthly_limit': 5,
          'monthly_used': 5,
          'reset_at': 1767225600,
        },
      });
      expect(errorDetailMessage(body), contains('5 calls'));
    });

    test('falls back to the raw code for an unknown map detail', () {
      final body = jsonEncode({
        'detail': {'error': 'something_else'},
      });
      expect(errorDetailMessage(body), 'something_else');
    });

    test('returns null for a body without a detail', () {
      expect(errorDetailMessage(jsonEncode({'message': 'nope'})), isNull);
      expect(errorDetailMessage('not json at all'), isNull);
    });
  });
}
