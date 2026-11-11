// Paid-start prompt transport: the server owns eligibility, claims, and route targets.
import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class FirstValuePrompt {
  const FirstValuePrompt({required this.kind, required this.route});

  final String kind;
  final String route;

  static FirstValuePrompt? fromResponse(String body) {
    try {
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      final prompt = decoded['prompt'];
      if (prompt == null) return null;
      if (prompt is! Map<String, dynamic>) throw const FormatException('invalid first-value prompt');
      final kind = prompt['kind'];
      final route = prompt['route'];
      if ((kind != 'capture' && kind != 'result') || route is! String || route.isEmpty) {
        throw const FormatException('invalid first-value prompt');
      }
      if (kind == 'capture' && route != '/settings/device') throw const FormatException('invalid capture route');
      if (kind == 'result' && !route.startsWith('/conversation/')) throw const FormatException('invalid result route');
      return FirstValuePrompt(kind: kind, route: route);
    } catch (_) {
      throw const FormatException('invalid first-value response');
    }
  }
}

class FirstValueApi {
  FirstValueApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';

  final String baseUrl;
  final ApiSend? send;

  Future<ApiResult<FirstValuePrompt?>> prompt({bool navigation = false}) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/prompt${navigation ? '?navigation=true&kind=result' : ''}',
          method: 'GET',
        ),
        decode: FirstValuePrompt.fromResponse,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));

  Future<ApiResult<bool>> recordResultOpen(String conversationId) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/result-open',
          method: 'POST',
          body: jsonEncode({'conversation_id': conversationId}),
        ),
        decode: (body) => ((jsonDecode(body) as Map<String, dynamic>)['recorded'] as num?) != null,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));

  Future<ApiResult<bool>> recordPendantConnection() => executeApi(
        request: ApiRequest(url: '${baseUrl}v1/first-value/recovery/pendant-connection', method: 'POST'),
        decode: (body) => (jsonDecode(body) as Map<String, dynamic>)['recorded'] == true,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
}
