import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
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
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/pending-work', method: 'GET'),
      decode: (body) => PendingWorkSnapshot.fromJson(_object(body)),
    );

Future<ApiResult<AttentionItemsPage>> getAttentionItems() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/attention-items', method: 'GET'),
      decode: (body) => AttentionItemsPage.fromJson(_object(body)),
    );

/// The server claims the retry once per failed attempt: a repeated or concurrent call returns the
/// same operation and starts no second paid run.
Future<ApiResult<AttentionRetryResult>> retryAttentionItem(String id, {required String idempotencyKey}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/${_id(id)}/retry',
        method: 'POST',
        headers: {'Idempotency-Key': idempotencyKey},
      ),
      decode: (body) => AttentionRetryResult.fromJson(id, _object(body)),
    );

/// Same [idempotencyKey], same answer: a double tap or a lost response replays, never re-runs.
Future<ApiResult<List<AttentionRetryResult>>> retryAllAttentionItems({required String idempotencyKey}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/retry-all',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'idempotency_key': idempotencyKey}),
      ),
      decode: (body) {
        final ops = _object(body)['operations'];
        if (ops is! List) throw const FormatException('Expected operations');
        return [
          for (final op in ops)
            if (op is Map<String, dynamic> && op['id'] is String) AttentionRetryResult.fromJson(op['id'] as String, op),
        ];
      },
    );

Future<ApiResult<void>> markAttentionItemsSeen(List<String> ids) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/attention-items/seen',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'ids': ids}),
      ),
      decode: (_) {},
    );

Future<ApiResult<void>> dismissAttentionItem(String id) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/attention-items/${_id(id)}/dismiss', method: 'POST'),
      decode: (_) {},
    );
