import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The picker list moved to the backend so a language can be added without an
/// app release. The bundled copy stays as the offline floor, so the behaviour
/// worth pinning is which source wins and what happens when the fetch fails.

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('source of the picker list', () {
    test('falls back to the bundled list before anything is fetched', () {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      // A first run with no network must still offer languages.
      expect(provider.availableLanguages, isNotEmpty);
      expect(provider.availableLanguages['English'], 'en');
    });

    test('a cached list from a previous session wins over the bundled copy', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode({'Swahili': 'sw', 'English': 'en'});

      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages();

      // Swahili is not in the bundled copy — proving the cache is being read.
      expect(provider.availableLanguages['Swahili'], 'sw');
    });

    test('a corrupt cache falls back instead of emptying the picker', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = 'not json';

      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages();

      expect(provider.availableLanguages['English'], 'en');
    });

    test('an empty cached map is ignored', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode(<String, String>{});

      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages();

      expect(provider.availableLanguages, isNotEmpty);
    });
  });

  group('getLanguageName', () {
    test('resolves a code the current list carries', () {
      final provider = HomeProvider();
      addTearDown(provider.dispose);
      expect(provider.getLanguageName('en'), 'English');
    });

    test('falls back to the bundled name for a code the server list dropped', () async {
      // The server list changes without an app release, so a stored preference
      // can outlive the list that offered it.
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode({'English': 'en'});
      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages();

      expect(provider.getLanguageName('ja'), 'Japanese');
    });

    test('returns the code itself for one nothing knows about', () {
      // Previously threw a StateError from firstWhere.
      final provider = HomeProvider();
      addTearDown(provider.dispose);
      expect(provider.getLanguageName('zz'), 'zz');
    });
  });
}
