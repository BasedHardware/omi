import 'dart:convert';
import 'dart:isolate';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/utils/off_ui_isolate.dart';

ApiResult<ActionItemsResponse> _tasksOffUiOnly(String body) {
  final ui = Isolate.current.debugName != 'action_items_parse';
  // ignore: avoid_print
  print('SCROLL_TASK_PAGE ui_json_decodes=${ui ? 1 : 0} rows=500 chars=${body.length}');
  if (ui) throw StateError('task page decoded on UI isolate');
  return decodeActionItemsEnvelope(body);
}

ActionItemsResponse _legacyTasksOffUiOnly(String body) {
  if (Isolate.current.debugName != 'action_items_parse') throw StateError('legacy task page decoded on UI isolate');
  return decodeLegacyActionItemsPage(body);
}

List<ServerMessage> _messagesOffUiOnly(String body) {
  final ui = Isolate.current.debugName != 'message_history_parse';
  // ignore: avoid_print
  print('SCROLL_CHAT_PAGE ui_json_decodes=${ui ? 1 : 0} rows=100 chars=${body.length}');
  if (ui) throw StateError('chat page decoded on UI isolate');
  return decodeMessageHistory(body);
}

ApiResult<ActionItemsResponse> _tasksInlineOnly(String body) {
  if (Isolate.current.debugName == 'action_items_parse') throw StateError('small task page spawned an isolate');
  return decodeActionItemsEnvelope(body);
}

List<ServerMessage> _messagesInlineOnly(String body) {
  if (Isolate.current.debugName == 'message_history_parse') throw StateError('small message page spawned an isolate');
  return decodeMessageHistory(body);
}

Map<String, dynamic> _task(int i) => {
      'id': 'task-$i',
      'description': 'Follow up with the team on the project plan and send a revised proposal for review.',
      'completed': false,
      'created_at': '2026-10-23T09:00:00Z',
      'due_at': '2026-10-25T09:00:00Z',
      'conversation_id': 'conversation-$i',
      'sort_order': i + 1,
    };

String _messagesBody(int count) => jsonEncode([
      for (var i = 0; i < count; i++)
        ServerMessage(
            'm$i',
            DateTime.utc(2026, 10, 23),
            List.filled(12, '**Project update**\n\n- Review the plan and send feedback.\n- Follow up tomorrow.')
                .join('\n\n'),
            MessageSender.ai,
            MessageType.text,
            null,
            false,
            [],
            [],
            []).toJson(),
    ]);

void main() {
  final originalTasks = actionItemsPageDecoder;
  final originalMessages = messageHistoryDecoder;
  final originalLegacy = legacyActionItemsPageDecoder;
  setUp(() => offUiIsolateFallbacks = 0);
  tearDown(() {
    actionItemsPageDecoder = originalTasks;
    legacyActionItemsPageDecoder = originalLegacy;
    messageHistoryDecoder = originalMessages;
  });

  test('500-task typed page parses without UI JSON decode or isolate fallback', () async {
    final body = jsonEncode({
      'action_items': [for (var i = 0; i < 500; i++) _task(i)],
      'has_more': true
    });
    expect(utf8.encode(body).length, greaterThan(64 * 1024));
    actionItemsPageDecoder = _tasksOffUiOnly;
    final result = await ActionItemsApi(
      baseUrl: 'http://127.0.0.1:1/',
      send: (_) async => http.Response(body, 200),
    ).list(limit: 500) as ApiSuccess<ActionItemsResponse>;
    expect(result.data.actionItems.map((t) => t.id), [for (var i = 0; i < 500; i++) 'task-$i']);
    expect(result.data.hasMore, isTrue);
    expect(result.rejectedRows, 0);
    expect(offUiIsolateFallbacks, 0);
  });

  test('100 markdown messages parse without UI JSON decode or isolate fallback', () async {
    final body = _messagesBody(100);
    expect(utf8.encode(body).length, greaterThan(64 * 1024));
    messageHistoryDecoder = _messagesOffUiOnly;
    final messages = await parseMessageHistory(body);
    expect(messages.map((m) => m.id), [for (var i = 0; i < 100; i++) 'm$i']);
    expect(messages.first.text, contains('**Project update**'));
    expect(offUiIsolateFallbacks, 0);
  });

  test('large legacy pages keep strict decoding off UI', () async {
    legacyActionItemsPageDecoder = _legacyTasksOffUiOnly;
    final rows = [for (var i = 0; i < 500; i++) _task(i)];
    expect((await parseLegacyActionItemsPage(jsonEncode({'action_items': rows, 'has_more': true}))).actionItems,
        hasLength(500));
    await expectLater(
        parseLegacyActionItemsPage(jsonEncode({
          'action_items': [...rows, 42]
        })),
        throwsA(anything));
    expect(offUiIsolateFallbacks, 0);
  });

  test('large partial typed page reports rejected rows once on caller isolate', () async {
    actionItemsPageDecoder = _tasksOffUiOnly;
    final events = <ApiFallbackEvent>[];
    // An unsendable telemetry sink must stay on the caller isolate.
    final port = ReceivePort();
    addTearDown(port.close);
    final result = await parseActionItemsPage(
      jsonEncode({
        'action_items': [for (var i = 0; i < 500; i++) _task(i), 42],
        'has_more': true
      }),
      fallback: (event) {
        port.sendPort.send('fallback');
        events.add(event);
      },
    ) as ApiSuccess<ActionItemsResponse>;
    expect(result.rejectedRows, 1);
    expect(result.data.actionItems, hasLength(500));
    expect(events.single.reason, ApiFallbackReason.partialDecode);
    expect(offUiIsolateFallbacks, 0);
  });

  test('large malformed and wholly invalid task pages remain decode failures', () async {
    for (final body in [
      '{${' ' * (64 * 1024)}',
      jsonEncode({'action_items': List.filled(70000, 42)})
    ]) {
      final result = await parseActionItemsPage(body);
      expect((result as ApiFailure<ActionItemsResponse>).problem.kind, ApiProblemKind.decode);
    }
    expect(offUiIsolateFallbacks, 0);
  });

  test('small task and message pages stay inline', () async {
    actionItemsPageDecoder = _tasksInlineOnly;
    messageHistoryDecoder = _messagesInlineOnly;
    final tasks = await parseActionItemsPage(jsonEncode({
      'action_items': [_task(0)],
      'has_more': false
    }));
    expect((tasks as ApiSuccess<ActionItemsResponse>).data.actionItems.single.id, 'task-0');
    expect((await parseMessageHistory(_messagesBody(1))).single.id, 'm0');
    expect(offUiIsolateFallbacks, 0);
  });
}
