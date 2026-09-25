import 'dart:io';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';

/// Language for a Custom STT provider.
///
/// Language is chosen in one place (docs/ux-contract.md §12): Settings → Language → Primary Language.
/// A Custom STT provider uses that language, mapped to the provider's code, unless the reader
/// explicitly overrides it for that provider on the Transcription page. The override is stored per
/// provider, next to the provider's saved config.
abstract final class SttLanguage {
  static String _key(SttProvider provider) => 'sttLanguageOverride_${provider.name}';

  /// The languages [provider] accepts, as offered on this platform (iOS has no auto-detect).
  static List<String> supported(SttProvider provider, {bool? isIOS}) {
    final languages = SttProviderConfig.get(provider).supportedLanguages;
    if (isIOS ?? Platform.isIOS) return languages.where((lang) => lang != 'multi').toList();
    return languages;
  }

  /// [primary] (a primary-language code such as `en`, `ko-KR` or `multi`) in [provider]'s codes, or
  /// null when the provider does not support it.
  static String? mapPrimary(SttProvider provider, String primary, {bool? isIOS}) {
    if (primary.isEmpty) return null;
    final languages = supported(provider, isIOS: isIOS);
    if (languages.contains(primary)) return primary;
    final base = primary.split(RegExp('[-_]')).first.toLowerCase();
    if (languages.contains(base)) return base;
    return null;
  }

  /// The language [provider] uses when it follows [primary]: the mapped primary language, else the
  /// provider's default.
  static String derived(SttProvider provider, String primary, {bool? isIOS}) {
    final mapped = mapPrimary(provider, primary, isIOS: isIOS);
    if (mapped != null) return mapped;
    final fallback = SttProviderConfig.get(provider).defaultLanguage;
    if ((isIOS ?? Platform.isIOS) && fallback == 'multi') return 'en';
    return fallback;
  }

  /// Whether [provider]'s language is explicitly overridden.
  ///
  /// Configs saved before the override existed carry no flag: a saved language that differs from
  /// both the provider default and the primary-derived language was picked by hand, so it counts as
  /// an override; anything else follows the primary language.
  static bool isOverridden(SttProvider provider, {CustomSttConfig? saved, String? primary}) {
    final stored = SharedPreferencesUtil().getString(_key(provider));
    if (stored.isNotEmpty) return stored == 'on';
    final language = saved?.language;
    if (language == null || language.isEmpty) return false;
    final defaults = SttProviderConfig.get(provider).defaultLanguage;
    final follows = derived(provider, primary ?? SharedPreferencesUtil().userPrimaryLanguage);
    return language != defaults && language != follows;
  }

  static Future<void> setOverridden(SttProvider provider, bool overridden) =>
      SharedPreferencesUtil().saveString(_key(provider), overridden ? 'on' : 'off');

  /// Rewrites every saved provider config that follows the primary language (and the active one) to
  /// [primary]. [previous] is the primary language before the change (for configs saved before the
  /// override flag existed). Returns true when the active Custom STT config changed, so the caller
  /// restarts transcription.
  static Future<bool> syncToPrimary(String primary, {required String previous}) async {
    final prefs = SharedPreferencesUtil();
    for (final provider in SttProvider.values) {
      if (provider == SttProvider.omi) continue;
      final saved = prefs.getConfigForProvider(provider);
      if (saved == null || isOverridden(provider, saved: saved, primary: previous)) continue;
      final language = derived(provider, primary);
      if (saved.language != language) {
        await prefs.saveConfigForProvider(provider, saved.copyWith(language: language));
      }
    }

    final active = prefs.customSttConfig;
    if (!active.isEnabled ||
        active.identity != null ||
        isOverridden(active.provider, saved: active, primary: previous)) {
      return false;
    }
    final language = derived(active.provider, primary);
    if (active.language == language) return false;
    await prefs.saveCustomSttConfig(active.copyWith(language: language));
    return true;
  }
}
