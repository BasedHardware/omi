import 'package:flutter_test/flutter_test.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_configuration.dart';

void main() {
  test('accepts a non-empty token and HTTPS Worker URL', () {
    const configuration = CloudflareTranscriptConfiguration(
      workerUrl: 'https://worker.example.test/base/',
      token: 'token',
    );

    expect(configuration.isConfigured, isTrue);
    expect(configuration.baseUri.toString(), 'https://worker.example.test/base');
  });

  test('requires a non-empty token even for a valid HTTPS Worker URL', () {
    const configuration = CloudflareTranscriptConfiguration(
      workerUrl: 'https://worker.example.test',
      token: '  ',
    );

    expect(configuration.isConfigured, isFalse);
  });

  test('accepts loopback HTTP Worker URLs for development tests', () {
    const configuration = CloudflareTranscriptConfiguration(
      workerUrl: 'http://localhost:8787/',
      token: 'token',
    );

    expect(configuration.isConfigured, isTrue);
    expect(configuration.baseUri.toString(), 'http://localhost:8787');
  });

  test('rejects public HTTP and structurally unsafe Worker URLs', () {
    const invalidWorkerUrls = [
      'http://worker.example.test',
      'https:///missing-authority',
      'https://credential@worker.example.test',
      'https://worker.example.test/?cursor=unexpected',
      'https://worker.example.test/#fragment',
    ];

    for (final workerUrl in invalidWorkerUrls) {
      final configuration = CloudflareTranscriptConfiguration(workerUrl: workerUrl, token: 'token');

      expect(configuration.isConfigured, isFalse, reason: workerUrl);
      expect(() => configuration.baseUri, throwsA(isA<CloudflareTranscriptConfigurationException>()));
    }
  });
}
