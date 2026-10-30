import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api_result.dart';

void main() {
  test('task detail GET addresses the backend id outside list pagination', () async {
    String? requested;
    final api = ActionItemsApi(
        baseUrl: 'http://127.0.0.1:8976/',
        send: (request) async {
          requested = request.url;
          return http.Response('{"id":"task-150","description":"Older task","completed":false}', 200);
        });

    final result = await api.getById('task-150');
    expect(requested, 'http://127.0.0.1:8976/v1/action-items/task-150');
    expect(result, isA<ApiSuccess>());
    expect((result as ApiSuccess).data.id, 'task-150');
  });

  test('task detail distinguishes a missing task from a server outage and bad JSON', () async {
    for (final (status, body, kind) in [
      (404, '{}', ApiProblemKind.notFound),
      (503, '{}', ApiProblemKind.server),
      (200, '{"id":1}', ApiProblemKind.decode),
    ]) {
      final api = ActionItemsApi(baseUrl: 'http://127.0.0.1:8976/', send: (_) async => http.Response(body, status));
      final result = await api.getById('task-150');
      expect(result, isA<ApiFailure>());
      expect((result as ApiFailure).problem.kind, kind);
    }
  });
}
