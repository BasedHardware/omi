// Task membership wire failures and filter input/continuation preservation.
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversation_tasks.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/off_ui_isolate.dart';

void main() {
  setUpAll(() => Env.overrideApiBaseUrl('http://127.0.0.1:18966/'));
  tearDownAll(Env.clearApiBaseUrlOverrideForTesting);
  test('presence contains boolean membership only; malformed successes stay failures', () async {
    for (final body in [
      '{}',
      '{"presence":{}}',
      '{"presence":{"a":"true"}}',
      '{"presence":{"a":true,"foreign":true}}'
    ]) {
      final result = await getConversationTaskPresence(['a'], send: (_) async => http.Response(body, 200));
      expect(result, isA<ApiFailure>());
    }
    final result =
        await getConversationTaskPresence(['a'], send: (_) async => http.Response('{"presence":{"a":false}}', 200));
    expect((result as ApiSuccess).data, {'a': false});
  });

  test('all filter inputs and opaque continuation reach the server in UTC', () async {
    final result = await getConversationsWithTasks(
        query: 'invoice',
        folderId: 'work',
        starred: true,
        startDate: DateTime.utc(2026, 1, 1),
        endDate: DateTime.utc(2026, 1, 2),
        cursor: 'signed-position',
        send: (request) async {
          expect(request.method, 'POST');
          expect(Uri.parse(request.url).path, endsWith('/v1/conversations/with-tasks/page'));
          expect(jsonDecode(request.body), {
            'query': 'invoice',
            'include_discarded': false,
            'folder_id': 'work',
            'starred': true,
            'start_date': '2026-01-01T00:00:00.000Z',
            'end_date': '2026-01-02T00:00:00.000Z',
            'cursor': 'signed-position',
            'limit': 25,
          });
          return http.Response('{"items":[],"next_cursor":"older","partial":true}', 200);
        });
    expect((result as ApiSuccess<TaskConversationPage>).data.nextCursor, 'older');
    expect(result.data.partial, isTrue);
  });

  test('large task page uses the conversation decode worker', () async {
    final completions = offUiIsolateWorkerCompletions;
    final fallbacks = offUiIsolateFallbacks;
    final body = '{"items":[],"next_cursor":null,"partial":false}${' ' * (70 * 1024)}';
    final result = await getConversationsWithTasks(send: (_) async => http.Response(body, 200));
    expect(result, isA<ApiSuccess<TaskConversationPage>>());
    expect(offUiIsolateWorkerCompletions, completions + 1);
    expect(offUiIsolateFallbacks, fallbacks);
  });

  test('bounded empty continuation is distinct from complete empty or failure', () async {
    for (final body in [
      '{"items":[],"next_cursor":null,"partial":true}',
      '{"items":[],"next_cursor":"","partial":false}',
      '{"items":[],"partial":"false"}',
      '{"items":[false],"partial":false}',
      '{"items":[{}],"partial":false}'
    ]) {
      expect(await getConversationsWithTasks(send: (_) async => http.Response(body, 200)), isA<ApiFailure>());
    }
    expect(await getConversationsWithTasks(send: (_) async => http.Response('error', 503)), isA<ApiFailure>());
    final empty =
        await getConversationsWithTasks(send: (_) async => http.Response('{"items":[],"partial":false}', 200));
    expect((empty as ApiSuccess<TaskConversationPage>).data.items, isEmpty);
  });
}
