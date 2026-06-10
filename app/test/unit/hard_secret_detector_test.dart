import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/hard_secret_detector.dart';

void main() {
  group('HardSecretDetector', () {
    test('detects credential-shaped secrets', () {
      expect(HardSecretDetector.contains('api key sk-1234567890abcdefghijklmnop'), isTrue);
      expect(HardSecretDetector.contains('password = correct-horse-battery-staple'), isTrue);
      expect(HardSecretDetector.contains('Authorization: bearer abcdefghijklmnopqrstuvwxyz123456'), isTrue);
      expect(HardSecretDetector.contains('-----BEGIN PRIVATE KEY-----'), isTrue);
    });

    test('does not classify email PII as a hard secret', () {
      expect(HardSecretDetector.contains('Reach me at user@example.com.'), isFalse);
      expect(HardSecretDetector.categories('Reach me at user@example.com.'), isEmpty);
    });

    test('returns stable sorted categories', () {
      final categories = HardSecretDetector.categories(
        'token=abcdefghijklmnopqrstuvwxyz123456 and password=superSecret123',
      );

      expect(categories, ['password', 'token']);
    });
  });
}
