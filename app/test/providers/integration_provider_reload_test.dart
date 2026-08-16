import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/providers/integration_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  IntegrationProvider providerWith(Map<String, bool> backend, {Map<String, bool>? prefs}) {
    return IntegrationProvider(
      fetchStatus: (appKey) async {
        if (!backend.containsKey(appKey)) return null;
        return IntegrationResponse(connected: backend[appKey]!, appKey: appKey);
      },
      saveStatus: (appKey, _) async {
        backend[appKey] = true;
        return true;
      },
      deleteStatus: (appKey) async {
        backend[appKey] = false;
        return true;
      },
      persistPref: (key, value) async {
        prefs?[key] = value;
        await SharedPreferencesUtil().saveBool(key, value);
      },
    );
  }

  test('cold start restores Apple Health after a previous successful connect', () async {
    final backend = <String, bool>{
      'google_calendar': false,
      'gmail': false,
      'apple_health': true,
    };
    final prefs = <String, bool>{};

    final first = providerWith(backend, prefs: prefs);
    addTearDown(first.dispose);
    await first.saveConnection(IntegrationApp.appleHealth.key, {});
    expect(first.isAppConnected(IntegrationApp.appleHealth), isTrue);

    // Process death: a new provider with empty memory must reload from backend.
    final restarted = providerWith(backend, prefs: prefs);
    addTearDown(restarted.dispose);
    expect(restarted.isAppConnected(IntegrationApp.appleHealth), isFalse);

    await restarted.loadFromBackend();

    expect(restarted.isAppConnected(IntegrationApp.appleHealth), isTrue);
    expect(prefs['apple_health_connected'], isTrue);
  });

  test('loadFromBackend fetches every surfaced IntegrationApp, not a hardcoded subset', () async {
    final requested = <String>[];
    final provider = IntegrationProvider(
      fetchStatus: (appKey) async {
        requested.add(appKey);
        return IntegrationResponse(connected: appKey == IntegrationApp.appleHealth.key, appKey: appKey);
      },
      persistPref: (_, __) async {},
    );
    addTearDown(provider.dispose);

    await provider.loadFromBackend();

    expect(
      requested.toSet(),
      equals(IntegrationApp.values.map((app) => app.key).toSet()),
    );
    for (final app in IntegrationApp.values) {
      expect(
        provider.isAppConnected(app),
        app == IntegrationApp.appleHealth,
        reason: '${app.key} should reflect the backend row after reload',
      );
    }
  });

  test('ensureLoaded hydrates once so chat can trust isAppConnected after restart', () async {
    var fetches = 0;
    final provider = IntegrationProvider(
      fetchStatus: (appKey) async {
        fetches++;
        return IntegrationResponse(connected: appKey == 'apple_health', appKey: appKey);
      },
      persistPref: (_, __) async {},
    );
    addTearDown(provider.dispose);

    expect(provider.hasLoaded, isFalse);
    await provider.ensureLoaded();
    expect(provider.hasLoaded, isTrue);
    expect(provider.isAppConnected(IntegrationApp.appleHealth), isTrue);

    final before = fetches;
    await provider.ensureLoaded();
    expect(fetches, before);
  });

  test('clearUserData forgets Apple Health as well as Google rows', () async {
    final prefs = <String, bool>{};
    final provider = providerWith({
      'google_calendar': true,
      'gmail': true,
      'apple_health': true,
    }, prefs: prefs);
    addTearDown(provider.dispose);

    await provider.loadFromBackend();
    expect(provider.isAppConnected(IntegrationApp.appleHealth), isTrue);

    provider.clearUserData();

    expect(provider.isAppConnected(IntegrationApp.appleHealth), isFalse);
    expect(provider.hasLoaded, isFalse);
    expect(prefs['apple_health_connected'], isFalse);
    expect(prefs['google_calendar_connected'], isFalse);
    expect(prefs['gmail_connected'], isFalse);
  });

  test('clearUserData mid-load does not resurrect the previous user', () async {
    final prefs = <String, bool>{};
    final persistStarted = Completer<void>();
    final releasePersist = Completer<void>();

    final provider = IntegrationProvider(
      fetchStatus: (appKey) async => IntegrationResponse(connected: true, appKey: appKey),
      persistPref: (key, value) async {
        prefs[key] = value;
        if (value) {
          if (!persistStarted.isCompleted) persistStarted.complete();
          await releasePersist.future;
        }
      },
    );
    addTearDown(provider.dispose);

    final load = provider.loadFromBackend();
    await persistStarted.future;
    provider.clearUserData();
    releasePersist.complete();
    await load;

    expect(provider.hasLoaded, isFalse);
    expect(provider.isLoading, isFalse);
    for (final app in IntegrationApp.values) {
      expect(provider.isAppConnected(app), isFalse, reason: '${app.key} leaked after logout');
      expect(prefs[IntegrationProvider.prefKeyFor(app.key)], isFalse);
    }
  });
}
