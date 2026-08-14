import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('coalesces duplicate catalog loads', () async {
    final provider = AppProvider();
    addTearDown(provider.dispose);
    final catalog = Completer<List<Map<String, dynamic>>>();
    var requestCount = 0;
    provider.retrieveAppsGroupedOverride = () {
      requestCount++;
      return catalog.future;
    };
    provider.getEnabledAppsOverride = () async => <String>[];
    Future<void>? reentrantLoad;
    provider.addListener(() {
      if (provider.isLoading) reentrantLoad ??= provider.getApps();
    });

    final first = provider.getApps();
    final second = provider.getApps();

    expect(requestCount, 1);
    expect(provider.isLoading, isTrue);
    catalog.complete(<Map<String, dynamic>>[]);
    await Future.wait([first, second, reentrantLoad!]);
    expect(provider.isLoading, isFalse);
  });

  test('allows catalog and popular loads to overlap without clearing loading early', () async {
    final provider = AppProvider();
    addTearDown(provider.dispose);
    final catalog = Completer<List<Map<String, dynamic>>>();
    final popular = Completer<List<App>>();
    provider.retrieveAppsGroupedOverride = () => catalog.future;
    provider.getEnabledAppsOverride = () async => <String>[];
    provider.retrievePopularAppsOverride = () => popular.future;

    final catalogLoad = provider.getApps();
    final popularLoad = provider.getPopularApps();
    expect(provider.isLoading, isTrue);

    popular.complete(<App>[]);
    await popularLoad;
    expect(provider.isLoading, isTrue);

    catalog.complete(<Map<String, dynamic>>[]);
    await catalogLoad;
    expect(provider.isLoading, isFalse);
  });

  test('coalesces duplicate popular app loads', () async {
    final provider = AppProvider();
    addTearDown(provider.dispose);
    final popular = Completer<List<App>>();
    var requestCount = 0;
    provider.retrievePopularAppsOverride = () {
      requestCount++;
      return popular.future;
    };

    final first = provider.getPopularApps();
    final second = provider.getPopularApps();

    expect(requestCount, 1);
    popular.complete(<App>[]);
    await Future.wait([first, second]);
    expect(provider.isLoading, isFalse);
  });
}
