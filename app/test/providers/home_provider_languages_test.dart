import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The picker list moved to the backend. What matters is which source wins.

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
      await provider.loadAvailableLanguages(fetch: () async => null);

      // Swahili is not in the bundled copy — proving the cache is being read.
      expect(provider.availableLanguages['Swahili'], 'sw');
    });

    test('a corrupt cache falls back instead of emptying the picker', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = 'not json';

      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages(fetch: () async => null);

      expect(provider.availableLanguages['English'], 'en');
    });

    test('an empty cached map is ignored', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode(<String, String>{});

      final provider = HomeProvider();
      addTearDown(provider.dispose);
      await provider.loadAvailableLanguages(fetch: () async => null);

      expect(provider.availableLanguages, isNotEmpty);
    });
  });

  group('the served list wins', () {
    test('over the bundled copy', () async {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadAvailableLanguages(fetch: () async => {'Swahili': 'sw'});

      expect(provider.availableLanguages, {'Swahili': 'sw'});
      expect(provider.availableLanguages.containsKey('Japanese'), isFalse);
    });

    test('over a cached list, and replaces the cache', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode({'Klingon': 'tlh'});
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadAvailableLanguages(fetch: () async => {'Welsh': 'cy'});

      expect(provider.availableLanguages, {'Welsh': 'cy'});
      expect(jsonDecode(SharedPreferencesUtil().cachedAvailableLanguages), {'Welsh': 'cy'});
    });

    test('a null fetch keeps the cached list and does not clear the cache', () async {
      SharedPreferencesUtil().cachedAvailableLanguages = jsonEncode({'Swahili': 'sw'});
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadAvailableLanguages(fetch: () async => null);

      expect(provider.availableLanguages, {'Swahili': 'sw'});
      expect(jsonDecode(SharedPreferencesUtil().cachedAvailableLanguages), {'Swahili': 'sw'});
    });

    test('a throwing fetch falls back to the bundled copy', () async {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadAvailableLanguages(fetch: () async => throw Exception('offline'));

      expect(provider.availableLanguages['English'], 'en');
    });

    test('an empty served list is ignored rather than emptying the picker', () async {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadAvailableLanguages(fetch: () async => <String, String>{});

      expect(provider.availableLanguages['English'], 'en');
    });
  });

  group('a sign-out mid-request', () {
    test('does not install the list it was fetching', () async {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadLanguagesThenSetupPrimary(fetch: () async {
        provider.clearUserData(); // signs out while the request is in flight
        return {'Swahili': 'sw'};
      });

      expect(provider.availableLanguages.containsKey('Swahili'), isFalse);
      expect(provider.availableLanguages['English'], 'en');
    });

    test('leaves the cache untouched', () async {
      final provider = HomeProvider();
      addTearDown(provider.dispose);

      await provider.loadLanguagesThenSetupPrimary(fetch: () async {
        provider.clearUserData();
        return {'Swahili': 'sw'};
      });

      expect(SharedPreferencesUtil().cachedAvailableLanguages, isEmpty);
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
      await provider.loadAvailableLanguages(fetch: () async => null);

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
