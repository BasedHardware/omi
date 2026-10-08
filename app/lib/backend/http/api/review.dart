import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/env/env.dart';

/// The Review queue, its recent-changes journal, and entity pages. Every call returns a typed
/// [ApiResult]. A 404 from `GET /v1/review/items` means the surface is off for this account; the
/// provider hides every entry point on it.

Map<String, dynamic> _object(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return decoded;
}

String _id(String id) => Uri.encodeComponent(id);

Future<ApiResult<ReviewItemsResponse>> getReviewItems() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/review/items', method: 'GET'),
      decode: (body) => ReviewItemsResponse.fromJson(_object(body)),
    );

/// Returns how many answerable items remain today.
Future<ApiResult<int>> answerReviewItem(ReviewItem item, ReviewAnswer answer) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/review/items/${_id(item.itemId)}/answer',
        method: 'POST',
        body: jsonEncode(answer.toJson(item.kind)),
      ),
      decode: (body) {
        final json = _object(body);
        final remaining = json['remaining_today'];
        return remaining is num ? remaining.toInt() : 0;
      },
    );

Future<ApiResult<ReviewChangesPage>> getReviewChanges({String? cursor}) {
  final query = cursor == null ? '' : '?${Uri(queryParameters: {'cursor': cursor}).query}';
  return executeApi(
    request: ApiRequest(url: '${Env.apiBaseUrl}v1/review/changes$query', method: 'GET'),
    decode: (body) => ReviewChangesPage.fromJson(_object(body)),
  );
}

Future<ApiResult<ReviewChange>> setReviewChangeUndone(String changeId, {required bool undone}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/review/changes/${_id(changeId)}/${undone ? 'undo' : 'redo'}',
        method: 'POST',
      ),
      decode: (body) {
        final change = ReviewChange.fromJson(_object(body));
        if (change == null) throw const FormatException('Malformed change');
        return change;
      },
    );

Future<ApiResult<EntityPageData>> getEntityPage(String entityId) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/entities/${_id(entityId)}/page', method: 'GET'),
      decode: (body) {
        final page = EntityPageData.fromJson(_object(body));
        if (page == null) throw const FormatException('Malformed entity page');
        return page;
      },
    );

Future<ApiResult<void>> postEntityCorrection(String entityId, String text) => executeApi<void>(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/entities/${_id(entityId)}/corrections',
        method: 'POST',
        body: jsonEncode({'text': text}),
      ),
      decode: (_) {},
    );

Future<ApiResult<List<EntityRef>>> getConversationEntities(String conversationId) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/conversations/${_id(conversationId)}/entities', method: 'GET'),
      decode: (body) => EntityRef.listFrom(_object(body)['entities']),
    );

Future<ApiResult<List<EntityRef>>> getProjectEntities() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/entities?type=project', method: 'GET'),
      decode: (body) => EntityRef.listFrom(_object(body)['entities']),
    );
