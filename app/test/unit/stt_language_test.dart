import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription/stt_language.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('mapping the primary language to a provider', () {
    test('uses the code, then its base language', () {
      expect(SttLanguage.mapPrimary(SttProvider.openai, 'es', isIOS: false), 'es');
      expect(SttLanguage.mapPrimary(SttProvider.openai, 'ko-KR', isIOS: false), 'ko');
      expect(SttLanguage.mapPrimary(SttProvider.openai, 'multi', isIOS: false), 'multi');
    });

    test('an unsupported primary language falls back to the provider default', () {
      expect(SttLanguage.mapPrimary(SttProvider.openai, 'tl', isIOS: false), isNull);
      expect(SttLanguage.derived(SttProvider.openai, 'tl', isIOS: false), 'en');
      expect(SttLanguage.derived(SttProvider.openai, '', isIOS: false), 'en');
    });

    test('iOS has no auto-detect', () {
      expect(SttLanguage.mapPrimary(SttProvider.openai, 'multi', isIOS: true), isNull);
      expect(SttLanguage.derived(SttProvider.omiParakeet, 'tl', isIOS: true), 'en');
    });
  });

  group('override state', () {
    test('an explicit flag wins', () async {
      await SttLanguage.setOverridden(SttProvider.openai, true);
      expect(SttLanguage.isOverridden(SttProvider.openai), isTrue);
      await SttLanguage.setOverridden(SttProvider.openai, false);
      expect(
        SttLanguage.isOverridden(
          SttProvider.openai,
          saved: const CustomSttConfig(provider: SttProvider.openai, language: 'fr'),
          primary: 'es',
        ),
        isFalse,
      );
    });

    test('without a flag, only a hand-picked language counts as an override', () {
      bool overridden(String? language) => SttLanguage.isOverridden(
            SttProvider.openai,
            saved: CustomSttConfig(provider: SttProvider.openai, language: language),
            primary: 'es',
          );
      expect(overridden(null), isFalse);
      expect(overridden('en'), isFalse, reason: 'the provider default');
      expect(overridden('es'), isFalse, reason: 'the primary language');
      expect(overridden('fr'), isTrue);
    });
  });

  test('a primary-language change reaches providers that follow it, not overridden ones', () async {
    final prefs = SharedPreferencesUtil();
    const following = CustomSttConfig(provider: SttProvider.openai, language: 'es', apiKey: 'k');
    const pinned = CustomSttConfig(provider: SttProvider.deepgram, language: 'fr');
    await prefs.saveConfigForProvider(SttProvider.openai, following);
    await prefs.saveConfigForProvider(SttProvider.deepgram, pinned);
    await SttLanguage.setOverridden(SttProvider.deepgram, true);
    await prefs.saveCustomSttConfig(following);

    final activeChanged = await SttLanguage.syncToPrimary('de', previous: 'es');

    expect(activeChanged, isTrue);
    expect(prefs.customSttConfig.language, 'de');
    expect(prefs.customSttConfig.apiKey, 'k');
    expect(prefs.getConfigForProvider(SttProvider.openai)?.language, 'de');
    expect(prefs.getConfigForProvider(SttProvider.deepgram)?.language, 'fr');
  });

  test('nothing changes when Omi transcribes', () async {
    expect(await SttLanguage.syncToPrimary('de', previous: 'es'), isFalse);
    expect(SharedPreferencesUtil().customSttConfig.isEnabled, isFalse);
  });
}
