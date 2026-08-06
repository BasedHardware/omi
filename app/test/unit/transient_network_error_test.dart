import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';

void main() {
  test('Android leave/background multipart abort is transient (#4587)', () {
    final abort = http.ClientException(
      'ClientSoftware caused connection abort',
      Uri.parse('https://api.omi.me/v2/sync-local-files'),
    );
    expect(isTransientNetworkError(abort), isTrue);
    expect(isTransientNetworkError(Exception('Software caused connection abort')), isTrue);
  });

  test('permanent HTTP errors are not transient', () {
    expect(isTransientNetworkError(Exception('401 Unauthorized')), isFalse);
    expect(isTransientNetworkError(Exception('Audio file could not be processed')), isFalse);
  });

  test('classic connectivity failures remain transient', () {
    expect(isTransientNetworkError(const SocketException('Network is unreachable')), isTrue);
    expect(isTransientNetworkError(http.ClientException('Connection reset by peer')), isTrue);
  });
}
