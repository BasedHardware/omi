import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/task_intelligence_wire.g.dart' as wire;

typedef TaskSuggestion = wire.GeneratedCandidateRecord;
typedef TaskSuggestionReceipt = wire.GeneratedCandidateResolutionReceipt;

/// Uses the same server-owned proposal, generation and acceptance contracts as desktop.
/// A summary request identifies a stored row; it never supplies a new task payload.
class TaskSuggestionsApi {
  TaskSuggestionsApi({required String baseUrl, ApiSend? send})
      : _baseUrl = baseUrl.endsWith('/') ? baseUrl : '$baseUrl/',
        _send = send;

  final String _baseUrl;
  final ApiSend? _send;

  Map<String, dynamic> _object(String body) {
    final value = jsonDecode(body);
    if (value is! Map<String, dynamic>) throw const FormatException('Expected object');
    return value;
  }

  Future<ApiResult<List<TaskSuggestion>>> list() => executeApi(
        request: ApiRequest(url: '${_baseUrl}v1/candidates?surface=suggested', method: 'GET'),
        send: _send,
        decode: (body) => wire.GeneratedCandidateListResponse.fromJson(_object(body)).candidates,
      );

  Future<ApiResult<TaskSuggestion>> get(String id) => executeApi(
        request: ApiRequest(url: '${_baseUrl}v1/candidates/${Uri.encodeComponent(id)}', method: 'GET'),
        send: _send,
        decode: (body) {
          final item = TaskSuggestion.fromJson(_object(body));
          if (item.candidateId != id) throw const FormatException('Candidate identity mismatch');
          return item;
        },
      );

  Future<ApiResult<int>> generation() => executeApi(
        request: ApiRequest(url: '${_baseUrl}v1/candidates/control', method: 'GET'),
        send: _send,
        decode: (body) {
          final generation = _object(body)['account_generation'];
          if (generation is! int || generation < 0) throw const FormatException('Invalid generation');
          return generation;
        },
      );

  Future<ApiResult<TaskSuggestion>> prepareSummary({
    required Map<String, dynamic> reference,
    required int generation,
    required String idempotencyKey,
  }) =>
      executeApi(
        request: ApiRequest(
          url: '${_baseUrl}v1/candidates/from-conversation',
          method: 'POST',
          headers: {'X-Account-Generation': '$generation', 'Idempotency-Key': idempotencyKey},
          body: jsonEncode(reference),
        ),
        send: _send,
        decode: (body) => TaskSuggestion.fromJson(_object(body)),
      );

  Future<ApiResult<TaskSuggestionReceipt>> accept(TaskSuggestion item, {Map<String, dynamic>? summary}) => executeApi(
        request: ApiRequest(
          url: '${_baseUrl}v1/candidates/${Uri.encodeComponent(item.candidateId)}/accept',
          method: 'POST',
          headers: {'X-Account-Generation': '${item.accountGeneration}'},
          body: jsonEncode({if (summary != null) 'summary_item': summary}),
        ),
        send: _send,
        decode: (body) {
          final receipt = TaskSuggestionReceipt.fromJson(_object(body));
          if (receipt.candidateId != item.candidateId ||
              receipt.status != 'accepted' ||
              receipt.taskId == null ||
              receipt.taskId!.isEmpty) {
            throw const FormatException('Missing saved task');
          }
          return receipt;
        },
      );

  Future<ApiResult<TaskSuggestionReceipt>> dismiss(TaskSuggestion item) => executeApi(
        request: ApiRequest(
          url: '${_baseUrl}v1/candidates/${Uri.encodeComponent(item.candidateId)}/reject',
          method: 'POST',
          headers: {'X-Account-Generation': '${item.accountGeneration}'},
          body: jsonEncode({'reason': 'not_useful'}),
        ),
        send: _send,
        decode: (body) {
          final receipt = TaskSuggestionReceipt.fromJson(_object(body));
          if (receipt.candidateId != item.candidateId || receipt.status != 'rejected') {
            throw const FormatException('Missing dismissal receipt');
          }
          return receipt;
        },
      );
}
