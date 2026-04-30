import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String _kLocaleKey = 'app.locale.v1';

/// Holds the current app locale. Wired into MaterialApp.locale so flipping it
/// from anywhere (e.g., the onboarding language step) re-renders the entire
/// app in the chosen language.
class LocaleProvider extends ChangeNotifier {
  Locale _locale = const Locale('en');
  bool _hydrated = false;

  Locale get locale => _locale;

  Future<void> hydrate() async {
    if (_hydrated) return;
    _hydrated = true;
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kLocaleKey);
    if (raw != null) {
      try {
        final json = jsonDecode(raw) as Map<String, dynamic>;
        final lang = json['lang'] as String?;
        final country = json['country'] as String?;
        if (lang != null && lang.isNotEmpty) {
          _locale = Locale(lang, country);
          notifyListeners();
        }
      } catch (_) {}
    }
  }

  Future<void> setFromLanguageId(String id) async {
    final next = _idToLocale(id);
    if (next == _locale) return;
    _locale = next;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _kLocaleKey,
      jsonEncode({'lang': next.languageCode, 'country': next.countryCode}),
    );
  }

  Future<void> reset() async {
    _locale = const Locale('en');
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kLocaleKey);
  }
}

Locale _idToLocale(String id) {
  switch (id) {
    case 'pt-BR':
    case 'pt':
      return const Locale('pt', 'BR');
    case 'en':
    default:
      return const Locale('en');
  }
}
