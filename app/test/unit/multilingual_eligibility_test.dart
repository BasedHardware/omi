import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/home_provider.dart';

/// #10022: client-side multi-language eligibility must mirror the backend's
/// live STT capability policy (Modulate auto-detection), not the retired
/// Deepgram Nova-3 list, including regional-variant normalization.
void main() {
  test('Modulate-supported languages are eligible for multi-language mode', () {
    for (final code in ['en', 'vi', 'ko', 'tr', 'ar', 'th', 'ja']) {
      expect(supportsLiveMultilingualMode(code), isTrue, reason: code);
    }
  });

  test('regional variants normalize to their base code', () {
    for (final code in ['en-US', 'pt-BR', 'vi-VN', 'zh_CN', 'fr-CA']) {
      expect(supportsLiveMultilingualMode(code), isTrue, reason: code);
    }
  });

  test('languages outside the live policy stay single-language', () {
    for (final code in ['my', 'am', 'lo', 'ne-NP']) {
      expect(supportsLiveMultilingualMode(code), isFalse, reason: code);
    }
  });
}
