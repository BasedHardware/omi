import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/gen/users_wire.g.dart';

/// #10022 follow-up: the client no longer mirrors the backend's multi-language
/// eligibility list — it trusts the server's `single_language_mode` in the
/// PATCH /v1/users/language response. This pins the wire contract that makes
/// that trust safe.
void main() {
  test('language update response carries the server-decided mode', () {
    final multilingual = GeneratedUserLanguageUpdateResponse.fromJson(
      {'status': 'ok', 'single_language_mode': false},
    );
    expect(multilingual.status, 'ok');
    expect(multilingual.singleLanguageMode, isFalse);

    final single = GeneratedUserLanguageUpdateResponse.fromJson(
      {'status': 'ok', 'single_language_mode': true},
    );
    expect(single.singleLanguageMode, isTrue);
  });

  test('a response without the mode field fails loudly instead of defaulting', () {
    expect(
      () => GeneratedUserLanguageUpdateResponse.fromJson({'status': 'ok'}),
      throwsA(isA<Object>()),
    );
  });
}
