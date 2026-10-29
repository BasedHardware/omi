import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';

/// Synthetic server boundary shared by hermetic tests and the native capture target.
class TaskDeliveryFixture {
  static const description = 'Send the project notes to the team';
  final requests = <ApiRequest>[];
  bool accepted = false;
  bool rejected = false;
  bool failHydration = false;
  bool projectSuggestion = false;
  int? expectedSummaryIndex;
  int acceptCalls = 0;
  int generation = 7;

  Map<String, dynamic> get candidate => {
        'account_generation': generation,
        'candidate_id': 'synthetic-candidate',
        'capture_confidence': 0.95,
        'created_at': '2026-10-20T08:00:00Z',
        'evidence_refs': [
          {'id': 'synthetic-conversation', 'kind': 'conversation', 'scope': 'private'}
        ],
        'idempotency_key': 'synthetic-capture-key',
        'ownership_confidence': 0.95,
        'proposed_action': 'create',
        'source_surface': 'conversation',
        'status': accepted ? 'accepted' : 'pending',
        'subject_kind': projectSuggestion ? 'workstream' : 'task',
        if (projectSuggestion)
          'workstream_proposal': {
            'title': 'Project launch',
            'objective': 'Share the agreed launch notes',
            'anchor_task': {'description': description, 'owner': 'self'},
          }
        else
          'task_change': {'description': description, 'owner': 'self'},
        if (accepted) 'result_task_id': 'synthetic-task',
      };

  Map<String, dynamic> get task => {
        'id': 'synthetic-task',
        'description': description,
        'completed': false,
        'conversation_id': 'synthetic-conversation',
      };

  http.Response response(Object body, [int status = 200]) => http.Response(jsonEncode(body), status);

  Future<http.Response> send(ApiRequest request) async {
    requests.add(request);
    final uri = Uri.parse(request.url);
    switch (uri.path) {
      case '/v1/action-items':
        if (request.method != 'GET') throw StateError('Manual task creation is forbidden in this journey');
        return response({
          'action_items': [if (accepted) task],
          'has_more': false
        });
      case '/v1/action-items/synthetic-task':
        return failHydration ? response({}, 503) : response(task);
      case '/v1/candidates':
        return response({
          'candidates': [if (!accepted && !rejected) candidate],
          'has_more': false
        });
      case '/v1/candidates/control':
        return response({'account_generation': generation});
      case '/v1/candidates/from-conversation':
        if (expectedSummaryIndex != null && jsonDecode(request.body)['action_item_index'] != expectedSummaryIndex) {
          return response({}, 409);
        }
        return response(candidate);
      case '/v1/candidates/synthetic-candidate/accept':
      case '/v1/candidates/synthetic-candidate/reject':
        if (request.headers['X-Account-Generation'] != '$generation') return response({}, 409);
        final accepting = uri.path.endsWith('/accept');
        final summary = request.body.isEmpty ? null : jsonDecode(request.body)['summary_item'];
        if (accepting &&
            summary != null &&
            expectedSummaryIndex != null &&
            summary['action_item_index'] != expectedSummaryIndex) {
          return response({}, 409);
        }
        if (accepting) {
          acceptCalls++;
          accepted = true;
        } else {
          rejected = true;
        }
        return response({
          'candidate_id': 'synthetic-candidate',
          'newly_resolved': true,
          'receipt_id': 'synthetic-receipt',
          'resolved_at': '2026-10-20T09:00:00Z',
          'status': accepting ? 'accepted' : 'rejected',
          if (accepting) 'task_id': 'synthetic-task',
        });
      default:
        throw StateError('Unexpected fixture route: ${request.method} ${uri.path}');
    }
  }
}
