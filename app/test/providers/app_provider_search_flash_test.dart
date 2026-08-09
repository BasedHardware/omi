import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';

typedef SearchResponse = ({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? filters});

/// What the apps screen would render from one notification.
///
/// The screen shows its loading placeholders while `isSearching`, and otherwise
/// shows results — falling back to "No apps found" when there are none. So a
/// notification carrying "not searching" and zero results *is* the empty state,
/// whatever happens afterwards.
typedef RenderedState = ({bool isSearching, int resultCount});

SearchResponse _response(List<App> apps) => (apps: apps, pagination: <String, dynamic>{}, filters: null);

App _app(String id, String name) => App(
      id: id,
      name: name,
      author: 'tester',
      description: 'test',
      image: '',
      capabilities: {'memories'},
      status: 'approved',
      category: 'test',
      approved: true,
      ratingCount: 0,
      enabled: false,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppProvider search queueing', () {
    late AppProvider provider;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      provider = AppProvider();
    });

    tearDown(() => provider.dispose());

    /// Types a query, then a longer one before the first request has come back.
    /// This is the ordinary case of someone typing faster than the network — it
    /// needs no error, no timeout, and no unusual state to reproduce.
    test('a superseded query never flashes the empty state before the newer one lands', () async {
      final firstRequest = Completer<SearchResponse>();
      final secondRequest = Completer<SearchResponse>();
      var requestCount = 0;

      provider.searchAppsOverride = ({
        String? query,
        String? category,
        double? minRating,
        String? capability,
        String? sort,
        bool? myApps,
        bool? installedApps,
        int offset = 0,
        int limit = 50,
      }) {
        requestCount++;
        return requestCount == 1 ? firstRequest.future : secondRequest.future;
      };

      final rendered = <RenderedState>[];
      provider.addListener(
        () => rendered.add((isSearching: provider.isSearching, resultCount: provider.filteredApps.length)),
      );

      provider.searchApps('a');
      await Future<void>.delayed(Duration.zero);
      provider.searchApps('adhd');
      await Future<void>.delayed(Duration.zero);

      // The first request returns results for a query the user has already moved
      // past, so they are correctly discarded.
      firstRequest.complete(_response([]));
      await Future<void>.delayed(Duration.zero);

      // The regression: discarding them must not also drop the searching state.
      // Doing so paints "No apps found" for a query that is still in flight.
      expect(
        rendered.where((state) => !state.isSearching && state.resultCount == 0),
        isEmpty,
        reason: 'the empty state was rendered while a newer query was still running',
      );

      secondRequest.complete(_response([_app('adhd-assistant', 'ADHD Assistant')]));
      await Future<void>.delayed(Duration.zero);

      expect(provider.isSearching, isFalse);
      expect(provider.filteredApps.map((app) => app.name), ['ADHD Assistant']);
      expect(requestCount, 2, reason: 'the queued query must still be run once the first returns');
    });

    test('the newest query wins even when an earlier request returns after it', () async {
      final firstRequest = Completer<SearchResponse>();
      final secondRequest = Completer<SearchResponse>();
      var requestCount = 0;

      provider.searchAppsOverride = ({
        String? query,
        String? category,
        double? minRating,
        String? capability,
        String? sort,
        bool? myApps,
        bool? installedApps,
        int offset = 0,
        int limit = 50,
      }) {
        requestCount++;
        return requestCount == 1 ? firstRequest.future : secondRequest.future;
      };

      provider.searchApps('a');
      await Future<void>.delayed(Duration.zero);
      provider.searchApps('adhd');
      await Future<void>.delayed(Duration.zero);

      firstRequest.complete(_response([_app('stale', 'Stale Result')]));
      await Future<void>.delayed(Duration.zero);
      secondRequest.complete(_response([_app('adhd-assistant', 'ADHD Assistant')]));
      await Future<void>.delayed(Duration.zero);

      expect(provider.filteredApps.map((app) => app.name), ['ADHD Assistant']);
    });

    test('a single search still settles out of the searching state', () async {
      provider.searchAppsOverride = ({
        String? query,
        String? category,
        double? minRating,
        String? capability,
        String? sort,
        bool? myApps,
        bool? installedApps,
        int offset = 0,
        int limit = 50,
      }) async =>
          _response([_app('adhd-assistant', 'ADHD Assistant')]);

      provider.searchApps('adhd');
      await Future<void>.delayed(Duration.zero);

      expect(provider.isSearching, isFalse);
      expect(provider.filteredApps, hasLength(1));
    });
  });
}
