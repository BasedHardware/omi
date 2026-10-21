import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/proactivity.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/services/auth_service.dart';
import '../../helpers/proactivity_fakes.dart';

class _UnusedAuth implements AuthService {
  @override
  dynamic noSuchMethod(Invocation invocation) => throw StateError('Auth should not be called');
}

void main() {
  test('adapter uses generated feed/outcome DTOs and exact public route', () async {
    final requests = <ApiRequest>[];
    final api = ProactivityApi(
      baseUrl: 'http://127.0.0.1:1/',
      send: (r) async {
        requests.add(r);
        return http.Response(
          jsonEncode(r.method == 'GET' ? feedResponse(items: [feedItem()]).toJson() : outcomeSuccess.data.toJson()),
          200,
        );
      },
    );
    final feed = await api.feed(cursor: 'opaque cursor');
    expect(feed, isA<ApiSuccess<GeneratedProactivityFeedResponse>>());
    expect(Uri.parse(requests.single.url).queryParameters, {'limit': '20', 'cursor': 'opaque cursor'});
    const event = GeneratedProactivityOutcomeRequest(
      action: 'shown',
      channel: 'feed',
      surface: 'ios',
      eventId: '123e4567-e89b-42d3-a456-426614174000',
    );
    expect(await api.outcome('item-1', event), isA<ApiSuccess<GeneratedProactivityOutcomeResponse>>());
    expect(requests.last.url, 'http://127.0.0.1:1/v1/proactivity/items/item-1/outcomes');
    expect(jsonDecode(requests.last.body), event.toJson());
  });
  test('adapter preserves 503 and malformed payload as typed failures', () async {
    for (final response in [http.Response('{}', 503), http.Response('{"enabled":null}', 200)]) {
      final api = ProactivityApi(baseUrl: 'http://127.0.0.1:1/', send: (_) async => response);
      expect(await api.feed(), isA<ApiFailure<GeneratedProactivityFeedResponse>>());
    }
  });
  test('owner change while auth headers build prevents transport under new account', () async {
    var current = true;
    var sends = 0;
    final result = await executeApi<String>(
      request: const ApiRequest(url: 'http://127.0.0.1:1/outcomes', method: 'POST'),
      canSend: () => current,
      decode: (s) => s,
      execution: ApiExecutionSeams(
        auth: _UnusedAuth(),
        headers: (r) async {
          current = false;
          return {};
        },
        transport: (r) async {
          sends++;
          return http.Response('{}', 200);
        },
      ),
    );
    expect(sends, 0);
    expect(result, isA<ApiFailure<String>>());
  });
}
