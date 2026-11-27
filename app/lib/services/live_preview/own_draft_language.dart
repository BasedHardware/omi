import 'package:omi/services/live_preview/live_preview_telemetry.dart';

/// Reliability experiment `live_words_cascade`: whether the phone's own recogniser may draft live
/// words for an account language.
///
/// The phone's recogniser handles one language per session. A multi-language account would get a
/// draft in the phone's own language whatever is spoken, and a language outside the recogniser's list
/// has no draft worth showing for the seconds before the vendor's words arrive. Those accounts see the
/// vendor's words only.
final class OwnDraftLanguage {
  OwnDraftLanguage._();

  /// Languages of the iOS 26 `SpeechTranscriber` locales (30 locales, read 2026-11-26 on iOS 26 and
  /// macOS 26: de, en, es, fr, it, ja, ko, pt, yue, zh). No Russian.
  static const appleLanguages = {'de', 'en', 'es', 'fr', 'it', 'ja', 'ko', 'pt', 'yue', 'zh'};

  static String code(String language) => language.trim().toLowerCase().split(RegExp('[-_]')).first;

  static bool allowed(String language, LivePreviewPlatform platform) {
    final spoken = code(language);
    if (spoken.isEmpty || spoken == 'multi') return false;
    if (platform == LivePreviewPlatform.ios) return appleLanguages.contains(spoken);
    return true;
  }
}
