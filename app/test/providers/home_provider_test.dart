import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/home_provider.dart';

void main() {
  group('getDeviceLanguageCodeFromLocale', () {
    final testLanguages = {
      'English': 'en',
      'Spanish': 'es',
      'Portuguese (Brazil)': 'pt-BR',
      'Portuguese (Portugal)': 'pt-PT',
      'Chinese (Simplified)': 'zh-CN',
      'Chinese (Traditional)': 'zh-TW',
      'Japanese': 'ja',
      'Korean': 'ko',
      'French': 'fr',
      'German': 'de',
    };

    test('exact match with full locale (e.g., pt-BR)', () {
      final locale = const Locale('pt', 'BR');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'pt-BR');
    });

    test('exact match with full locale (e.g., zh-CN)', () {
      final locale = const Locale('zh', 'CN');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'zh-CN');
    });

    test('exact match with full locale (e.g., zh-TW)', () {
      final locale = const Locale('zh', 'TW');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'zh-TW');
    });

    test('base language match when no country specified (e.g., en matches en)', () {
      final locale = const Locale('en');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'en');
    });

    test('base language match when country not in list (e.g., en-GB matches en)', () {
      final locale = const Locale('en', 'GB');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'en');
    });

    test('base language match for Japanese (ja-JP matches ja)', () {
      final locale = const Locale('ja', 'JP');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'ja');
    });

    test('base language match for Korean (ko-KR matches ko)', () {
      final locale = const Locale('ko', 'KR');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'ko');
    });

    test('base language match for French (fr-CA matches fr)', () {
      final locale = const Locale('fr', 'CA');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'fr');
    });

    test('base language match for German (de-AT matches de)', () {
      final locale = const Locale('de', 'AT');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'de');
    });

    test('fallback returns null for unsupported language', () {
      final locale = const Locale('sw'); // Swahili - not in list
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, isNull);
    });

    test('fallback returns null for unsupported language with country', () {
      final locale = const Locale('ar', 'SA'); // Arabic - not in list
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, isNull);
    });

    test('handles empty languages map', () {
      final locale = const Locale('en', 'US');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, {});
      expect(result, isNull);
    });

    test('case insensitive matching for language codes', () {
      final locale = const Locale('EN', 'us');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'en');
    });

    test('prefers exact match over base match', () {
      // pt-BR should match pt-BR exactly, not just pt
      final locale = const Locale('pt', 'BR');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      expect(result, 'pt-BR');
    });

    test('Portuguese without country falls back to first Portuguese variant', () {
      final locale = const Locale('pt');
      final result = HomeProvider.getDeviceLanguageCodeFromLocale(locale, testLanguages);
      // Should match one of the Portuguese variants by base language
      expect(result, anyOf('pt-BR', 'pt-PT'));
    });
  });
}
