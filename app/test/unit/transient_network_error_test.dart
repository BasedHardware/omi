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
    expect(isTransientNetworkError(Exception('software caused connection abort')), isTrue);
  });

  test('standalone ClientSoftware token is not treated as transient', () {
    expect(isTransientNetworkError(Exception('ClientSoftware HTTP 400')), isFalse);
  });

  test('permanent HTTP errors are not transient', () {
    expect(isTransientNetworkError(Exception('401 Unauthorized')), isFalse);
    expect(isTransientNetworkError(Exception('Audio file could not be processed')), isFalse);
  });

  test('classic connectivity failures remain transient', () {
    expect(isTransientNetworkError(const SocketException('Network is unreachable')), isTrue);
    expect(isTransientNetworkError(http.ClientException('Connection reset by peer')), isTrue);
  });

  test('a connection dropped mid-upload is transient in the shape package:http reports it', () {
    final uri = Uri.parse('https://api.omi.me/v2/sync-local-files?audio_start_seconds=1792927415.0');
    // Messages Crashlytics recorded for /v2/sync-local-files uploads (iOS and Android).
    const messages = [
      "Can't assign requested address",
      'Cannot assign requested address',
      'Operation timed out',
      'Connection timed out',
      'No route to host',
      'Broken pipe',
      'Read failed',
      'Write failed',
      '\n\tSSLV3_ALERT_BAD_RECORD_MAC(tls_record.cc:486) error 268436476',
    ];
    for (final message in messages) {
      final error = http.ClientException(message, uri);
      expect(error, isNot(isA<SocketException>()), reason: 'the production shape has no SocketException type');
      expect(isTransientNetworkError(error), isTrue, reason: message);
    }
  });

  test('EADDRNOTAVAIL (errno 49) as a SocketException is transient', () {
    const error = SocketException('Write failed', osError: OSError("Can't assign requested address", 49));
    expect(isTransientNetworkError(error), isTrue);
  });

  test('client and file errors that share those words stay reportable', () {
    expect(isTransientNetworkError(http.ClientException('TLSV1_ALERT_PROTOCOL_VERSION(tls_record.cc:486)')), isFalse);
    expect(isTransientNetworkError(http.ClientException('HTTP request failed. Client is already closed.')), isFalse);
    expect(isTransientNetworkError(const FileSystemException('Read failed', '/wals/audio_1000.bin')), isFalse);
  });
}
