import 'package:flutter/material.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocaleProvider extends ChangeNotifier {
  static const String _localeKey = 'app_locale';

  Locale? _locale;
  bool _initialized = false;

  LocaleProvider() {
    _loadSavedLocale();
  }

  /// The current app locale. If null, the app uses the system locale.
  Locale? get locale => _locale;

  bool get isInitialized => _initialized;

  Future<void> _loadSavedLocale() async {
    final prefs = await SharedPreferences.getInstance();
    final localeCode = prefs.getString(_localeKey);
    if (localeCode != null) {
      _locale = Locale(localeCode);
    } else {
      final deviceLocale = WidgetsBinding.instance.platformDispatcher.locale;
      // Check if the device locale is supported
      if (AppLocalizations.supportedLocales.any((locale) => locale.languageCode == deviceLocale.languageCode)) {
        _locale = Locale(deviceLocale.languageCode);
      } else {
        _locale = const Locale('en');
      }
      // Save the default choice so it persists as an explicit selection
      await prefs.setString(_localeKey, _locale!.languageCode);
    }
    _initialized = true;
    notifyListeners();
  }

  /// Set the app locale.
  Future<void> setLocale(Locale? locale) async {
    if (locale == null) return; // Do not allow setting to null (System Default)
    _locale = locale;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_localeKey, locale.languageCode);
    notifyListeners();
  }

  /// Get the display name for a locale.
  static String getDisplayName(Locale locale) {
    switch (locale.languageCode) {
      case 'en':
        return 'English';
      case 'ja':
        return '日本語 (Japanese)';
      case 'es':
        return 'Español (Spanish)';
      case 'fr':
        return 'Français (French)';
      case 'de':
        return 'Deutsch (German)';
      case 'zh':
        return '中文 (Chinese)';
      case 'ko':
        return '한국어 (Korean)';
      case 'pt':
        return 'Português (Portuguese)';
      case 'ar':
        return 'العربية (Arabic)';
      case 'hi':
        return 'हिंदी (Hindi)';
      default:
        return locale.languageCode;
    }
  }

  static List<Locale> get supportedLocales => AppLocalizations.supportedLocales;
}
