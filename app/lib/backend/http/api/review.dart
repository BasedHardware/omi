import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;
import 'package:omi/backend/schema/gen/entity_pages_wire.g.dart' as entity_wire;
import 'package:omi/env/env.dart';

/// The Review queue, its recent-changes journal, and entity pages. Every call returns a typed
/// [ApiResult]. A 404 from `GET /v1/review/items` means the surface is off for this account; the
/// provider hides every entry point on it.

Object? _objectReviver(Object? key, Object? value) {
  if (key == null && value is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return value;
}

String _id(String id) => Uri.encodeComponent(id);

Future<ApiResult<ReviewItemsResponse>> getReviewItems() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/review/items', method: 'GET'),
      decode: (body) => ReviewItemsResponse.fromGenerated(
        wire.GeneratedReviewItemsResponse.fromJson(jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>),
      ),
    );

/// Returns how many answerable items remain today.
Future<ApiResult<int>> answerReviewItem(ReviewItem item, ReviewAnswer answer) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/review/items/${_id(item.itemId)}/answer',
        method: 'POST',
        body: jsonEncode(answer.toJson(item.kind)),
      ),
      decode: (body) =>
          wire.GeneratedReviewAnswerReceipt.fromJson(jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>)
              .remainingToday,
    );

Future<ApiResult<ReviewChangesPage>> getReviewChanges({String? cursor}) {
  final url = Uri.parse('${Env.apiBaseUrl}v1/review/changes');
  return executeApi(
    request: ApiRequest(
      url: (cursor == null ? url : url.replace(queryParameters: {'cursor': cursor})).toString(),
      method: 'GET',
    ),
    decode: (body) => ReviewChangesPage.fromGenerated(
      wire.GeneratedReviewChangesResponse.fromJson(jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>),
    ),
  );
}

Future<ApiResult<ReviewChange>> setReviewChangeUndone(String changeId, {required bool undone}) => executeApi(
      request: ApiRequest(
        url: undone
            ? '${Env.apiBaseUrl}v1/review/changes/${_id(changeId)}/undo'
            : '${Env.apiBaseUrl}v1/review/changes/${_id(changeId)}/redo',
        method: 'POST',
      ),
      decode: (body) {
        return ReviewChange.fromGenerated(
            wire.GeneratedReviewChange.fromJson(jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>));
      },
    );

Future<ApiResult<EntityPageData>> getEntityPage(String entityId) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/entities/${_id(entityId)}/page', method: 'GET'),
      decode: (body) {
        return EntityPageData.fromGenerated(
          entity_wire.GeneratedEntityPage.fromJson(jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>),
        );
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
      decode: (body) => EntityRef.listFrom(
        entity_wire.GeneratedEntitiesResponse.fromJson(
                jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>)
            .toJson()['entities'],
      ),
    );

Future<ApiResult<List<EntityRef>>> getProjectEntities() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/entities?type=project', method: 'GET'),
      decode: (body) => EntityRef.listFrom(
        entity_wire.GeneratedEntitiesResponse.fromJson(
                jsonDecode(body, reviver: _objectReviver) as Map<String, dynamic>)
            .toJson()['entities'],
      ),
    );

/// Tells the backend which release channel this install is on, so early features can follow
/// TestFlight without trusting the client for anything else. 404 while the backend has it off.
Future<ApiResult<void>> putReleaseChannel(String channel, {int? appBuild}) => executeApi<void>(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/users/release-channel',
        method: 'PUT',
        body: jsonEncode({'release_channel': channel, if (appBuild != null) 'app_build': appBuild}),
      ),
      decode: (_) {},
    );
