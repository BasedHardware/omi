import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/stt_request_credentials.dart';

void main() {
  test('Deepgram key rotation preserves custom request settings', () {
    final request = {
      'url': 'wss://fixture.invalid/listen',
      'headers': {'authorization': 'Token old-fixture-key', 'X-Custom': 'keep'},
      'params': {'model': 'nova-3', 'smart_format': 'true'},
    };
    final rotated = jsonDecode(updateSttRequestApiKey(
      provider: SttProvider.deepgramLive,
      requestJson: jsonEncode(request),
      previousKey: 'old-fixture-key',
      nextKey: 'new-fixture-key',
    ));
    expect(rotated, {
      ...request,
      'headers': {'authorization': 'Token new-fixture-key', 'X-Custom': 'keep'},
    });
  });

  test('deliberate authorization override is preserved', () {
    final request = jsonEncode({
      'headers': {'Authorization': 'Token explicit-fixture-key'}
    });
    expect(
      updateSttRequestApiKey(
        provider: SttProvider.deepgramLive,
        requestJson: request,
        previousKey: 'old-fixture-key',
        nextKey: 'new-fixture-key',
      ),
      request,
    );
  });

  test('clearing the key removes the old generated credential', () {
    final rotated = updateSttRequestApiKey(
      provider: SttProvider.deepgramLive,
      requestJson: jsonEncode({
        'headers': {'Authorization': 'Token old-fixture-key'}
      }),
      previousKey: 'old-fixture-key',
      nextKey: '',
    );
    expect(jsonDecode(rotated)['headers']['Authorization'], 'Token ');
    expect(rotated, isNot(contains('old-fixture-key')));
  });

  for (final request in ['{invalid', '[]', '{"headers":[]}', '{}']) {
    test('incomplete request remains available to validation: $request', () {
      expect(
        updateSttRequestApiKey(
          provider: SttProvider.deepgramLive,
          requestJson: request,
          previousKey: 'old-fixture-key',
          nextKey: 'new-fixture-key',
        ),
        request,
      );
    });
  }
}
