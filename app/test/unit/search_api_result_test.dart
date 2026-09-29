import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

void main() {
  setUp(() => Env.overrideApiBaseUrl('https://search.test.invalid/'));
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('overview decodes counts and folders through the send seam', () async {
    final result = await getSearchOverview(
      send: (request) async {
        expect(Uri.parse(request.url).path, '/v1/search/overview');
        expect(request.method, 'GET');
        return http.Response(
          jsonEncode({
            'starred': 2,
            'recaps': 3,
            'folders': [
              {'id': 'f1', 'name': 'Work', 'icon': 'folder', 'color': '#123456', 'count': 4},
            ],
          }),
          200,
        );
      },
    );
    final overview = (result as ApiSuccess<SearchOverview>).data;
    expect(overview.starred, 2);
    expect(overview.recaps, 3);
    expect(overview.folders.single.id, 'f1');
    expect(overview.folders.single.count, 4);
  });

  test('overview accepts an empty response object', () async {
    final result = await getSearchOverview(send: (_) async => http.Response('{}', 200));
    final overview = (result as ApiSuccess<SearchOverview>).data;
    expect(overview.starred, isNull, reason: 'an absent count shows no number, never a false 0');
    expect(overview.folders, isEmpty);
  });

  test('overview reports a missing route and malformed 2xx separately', () async {
    final missing = await getSearchOverview(send: (_) async => http.Response('{}', 404));
    expect((missing as ApiFailure<SearchOverview>).problem.kind, ApiProblemKind.notFound);

    final malformed = await getSearchOverview(send: (_) async => http.Response('[]', 200));
    expect((malformed as ApiFailure<SearchOverview>).problem.kind, ApiProblemKind.decode);
  });

  test('action item search decodes a hit and encoded query', () async {
    final result = await searchActionItems(
      'plan & ship',
      limit: 3,
      send: (request) async {
        final uri = Uri.parse(request.url);
        expect(uri.path, '/v1/action-items/search');
        expect(uri.queryParameters, {'query': 'plan & ship', 'limit': '3'});
        return http.Response(
          jsonEncode({
            'action_items': [
              {'id': 'a1', 'description': 'Plan launch', 'completed': false},
            ],
          }),
          200,
        );
      },
    );
    expect((result as ApiSuccess).data.single.id, 'a1');
  });

  test('action item search preserves a valid empty list', () async {
    final result = await searchActionItems('none', send: (_) async => http.Response('{"action_items":[]}', 200));
    expect((result as ApiSuccess).data, isEmpty);
  });

  test('action item search reports server and missing-envelope failures', () async {
    final outage = await searchActionItems('task', send: (_) async => http.Response('{}', 500));
    expect((outage as ApiFailure).problem.kind, ApiProblemKind.server);

    final malformed = await searchActionItems('task', send: (_) async => http.Response('{}', 200));
    expect((malformed as ApiFailure).problem.kind, ApiProblemKind.decode);
  });
}
