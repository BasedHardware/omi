// Read-only task membership and cursor-page transport. Invalid responses stay
// typed failures; no task text or speculative empty-success fallback is exposed.
import 'dart:convert';

import 'package:omi/backend/http/api/conversations.dart' show ConversationApi;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';

class TaskConversationPage {
  const TaskConversationPage({required this.items, this.nextCursor, this.partial = false});

  final List<ServerConversation> items;
  final String? nextCursor;
  final bool partial;
}

Map<String, dynamic> _object(String body) {
  final json = jsonDecode(body);
  if (json is! Map<String, dynamic>) throw const FormatException('Expected object');
  return json;
}

Future<ApiResult<Map<String, bool>>> getConversationTaskPresence(
  List<String> ids, {
  ApiSend? send,
  bool Function()? canSend,
}) =>
    executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/conversations/task-presence',
        method: 'POST',
        body: jsonEncode({'conversation_ids': ids}),
      ),
      send: send,
      canSend: canSend,
      decode: (body) {
        final presence = _object(body)['presence'];
        if (presence is! Map<String, dynamic> ||
            ids.any((id) => presence[id] is! bool) ||
            presence.keys.any((id) => !ids.contains(id))) {
          throw const FormatException('Invalid task presence');
        }
        return presence.cast<String, bool>();
      },
    );

Future<ApiResult<TaskConversationPage>> getConversationsWithTasks({
  String query = '',
  bool includeDiscarded = false,
  String? folderId,
  bool? starred,
  DateTime? startDate,
  DateTime? endDate,
  String? cursor,
  ApiSend? send,
  bool Function()? canSend,
}) async {
  final sent = await executeApi<String>(
    request: ApiRequest(
      url: '${Env.apiBaseUrl}v1/conversations/with-tasks/page',
      method: 'POST',
      body: jsonEncode({
        'query': query,
        'include_discarded': includeDiscarded,
        'folder_id': folderId,
        'starred': starred,
        'start_date': startDate?.toUtc().toIso8601String(),
        'end_date': endDate?.toUtc().toIso8601String(),
        'cursor': cursor,
        'limit': 25,
      }),
    ),
    send: send,
    canSend: canSend,
    decode: (body) => body,
  );
  switch (sent) {
    case ApiFailure(:final problem):
      return ApiFailure(problem);
    case ApiSuccess(:final data, :final truncated):
      try {
        final page = await ConversationApi.decodeOffUi(data, _decodeTaskPage);
        return ApiSuccess(page, truncated: truncated);
      } on FormatException {
        return const ApiFailure(ApiProblem(ApiProblemKind.decode));
      }
  }
}

TaskConversationPage _decodeTaskPage(String body) {
  final json = _object(body);
  if (json['items'] is! List ||
      json['partial'] is! bool ||
      (json['next_cursor'] != null && json['next_cursor'] is! String)) {
    throw const FormatException('Invalid task conversation page');
  }
  final next = json['next_cursor'] as String?;
  if (next?.isEmpty == true || (json['partial'] == true && next == null)) {
    throw const FormatException('Invalid task filter continuation');
  }
  final rows = <ServerConversation>[];
  try {
    for (final row in json['items']) {
      if (row is! Map<String, dynamic>) throw const FormatException('Invalid conversation row');
      rows.add(ServerConversation.fromJson(row));
    }
  } on TypeError {
    throw const FormatException('Invalid conversation row');
  }
  return TaskConversationPage(
    items: rows,
    nextCursor: next,
    partial: json['partial'],
  );
}
