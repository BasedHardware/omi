import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/env/env.dart';

/// Thin transport boundary: wire DTOs are generated from the public contract.
class ProactivityApi {
  ProactivityApi({String? baseUrl, this.send, this.canSend}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';

  final String baseUrl;
  final ApiSend? send;
  final bool Function()? canSend;

  Map<String, dynamic> _object(String body) {
    final value = jsonDecode(body);
    if (value is! Map<String, dynamic>) throw const FormatException('Expected object');
    return value;
  }

  Future<ApiResult<GeneratedProactivityFeedResponse>> feed({String cursor = ''}) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/proactivity/feed?${Uri(queryParameters: {'limit': '20', 'cursor': cursor}).query}',
          method: 'GET',
        ),
        decode: (body) => GeneratedProactivityFeedResponse.fromJson(_object(body)),
        send: send,
        canSend: canSend,
      );

  Future<ApiResult<GeneratedProactivityOutcomeResponse>> outcome(
    String itemId,
    GeneratedProactivityOutcomeRequest outcome,
  ) =>
      executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/proactivity/items/${Uri.encodeComponent(itemId)}/outcomes',
          method: 'POST',
          body: jsonEncode(outcome.toJson()),
        ),
        decode: (body) => GeneratedProactivityOutcomeResponse.fromJson(_object(body)),
        send: send,
        canSend: canSend,
      );
}
