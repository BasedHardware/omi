import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/pending_work_wire.g.dart' as wire;
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/env/env.dart';

/// Pending work and Needs attention. Every call returns a typed [ApiResult]. While the backend gate
/// is off the reads answer `enabled: false`; an older backend answers 404, which callers treat the
/// same way.

Map<String, dynamic> _object(String body) {
  final json = jsonDecode(body);
  if (json is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return json;
}

String _id(String id) => Uri.encodeComponent(id);

Future<ApiResult<PendingWorkSnapshot>> getPendingWork() => executeApi(
      request: ApiRequest(
          url: '${Env.apiBaseUrl}v1/pending-work', method: 'GET', headers: const {'X-Omi-Home-Ownership': '1'}),
      decode: (body) => PendingWorkSnapshot.fromGenerated(wire.GeneratedPendingWorkSnapshot.fromJson(_object(body))),
    );

// The ledger contract requires identity/kind/retry only. Older generated DTOs
// require display metadata too; supply absent metadata without inventing UI text.
Map<String, dynamic> _attentionWireObject(Map<String, dynamic> json) => {
      'enabled': true,
      'unseen_count': 0,
      ...json,
      'items': [
        for (final item in (json['items'] as List? ?? const []))
          if (item is Map)
            {
              'created_at': '1970-01-01T00:00:00Z',
              'duration_seconds': 0,
              'failure_code': '',
              'seen': false,
              'started_at': null,
              'title': null,
              ...Map<String, dynamic>.from(item),
            }
      ],
    };

Future<ApiResult<AttentionItemsPage>> getAttentionItems({ApiSend? send}) => executeApi(
      send: send,
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/attention-items', method: 'GET'),
      decode: (body) => AttentionItemsPage.fromGenerated(
          wire.GeneratedAttentionItemsPage.fromJson(_attentionWireObject(_object(body)))),
    );

/// The server claims the retry once per failed attempt: a repeated or concurrent call returns the
/// same operation and starts no second paid run.
Future<ApiResult<AttentionRetryResult>> retryAttentionItem(String id,
        {required String idempotencyKey, ApiSend? send}) =>
    executeApi(
      send: send,
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/${_id(id)}/retry',
        method: 'POST',
        headers: {'Idempotency-Key': idempotencyKey},
      ),
      decode: (body) =>
          AttentionRetryResult.fromGenerated(id, wire.GeneratedAttentionRetryResponse.fromJson(_object(body))),
    );

/// Same [idempotencyKey], same answer: a double tap or a lost response replays, never re-runs.
Future<ApiResult<List<AttentionRetryResult>>> retryAllAttentionItems({required String idempotencyKey}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/retry-all',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(wire.GeneratedRetryAllRequest(idempotencyKey: idempotencyKey).toJson()),
      ),
      decode: (body) => [
        for (final op in wire.GeneratedAttentionRetryAllResponse.fromJson(_object(body)).operations)
          AttentionRetryResult.fromGenerated(op.id, op),
      ],
    );

Future<ApiResult<void>> markAttentionItemsSeen(List<String> ids) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/seen',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(wire.GeneratedSeenRequest(ids: ids).toJson()),
      ),
      decode: (_) {},
    );

Future<ApiResult<void>> dismissAttentionItem(String id) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/attention-items/${_id(id)}/dismiss', method: 'POST'),
      decode: (_) {},
    );
