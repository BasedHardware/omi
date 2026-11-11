// Paid-start prompt transport: the server owns eligibility, claims, and route targets.
import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class FirstValuePrompt {
  const FirstValuePrompt({required this.kind, required this.route});

  final String kind;
  final String route;
}

class FirstValueResponse {
  const FirstValueResponse(this.prompt);
  const FirstValueResponse.empty() : prompt = null;

  final FirstValuePrompt? prompt;

  static FirstValueResponse fromResponse(String body) {
    final decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic>) throw const FormatException('invalid first-value response');
    final raw = decoded['prompt'];
    if (raw == null) return const FirstValueResponse.empty();
    if (raw is! Map<String, dynamic>) throw const FormatException('invalid first-value prompt');
    final kind = raw['kind'];
    final route = raw['route'];
    if ((kind != 'capture' && kind != 'result') || route is! String || route.isEmpty) {
      throw const FormatException('invalid first-value prompt');
    }
    if (kind == 'capture' && route != '/settings/device') throw const FormatException('invalid capture route');
    if (kind == 'result' && !route.startsWith('/conversation/')) throw const FormatException('invalid result route');
    return FirstValueResponse(FirstValuePrompt(kind: kind, route: route));
  }
}

bool _recordedOutcome(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic> || decoded['recorded'] is! num) {
    throw const FormatException('invalid result-open response');
  }
  return true;
}

bool _recordedPendantConnection(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic> || decoded['recorded'] is! bool) {
    throw const FormatException('invalid pendant-connection response');
  }
  return decoded['recorded'] as bool;
}

class FirstValueApi {
  FirstValueApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';

  final String baseUrl;
  final ApiSend? send;

  Future<ApiResult<FirstValueResponse>> prompt({bool navigation = false}) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/prompt${navigation ? '?navigation=true&kind=result' : ''}',
          method: 'GET',
        ),
        decode: FirstValueResponse.fromResponse,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));

  Future<ApiResult<bool>> recordResultOpen(String conversationId) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/result-open',
          method: 'POST',
          body: jsonEncode({'conversation_id': conversationId}),
        ),
        decode: _recordedOutcome,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));

  Future<ApiResult<bool>> recordPendantConnection() => executeApi(
        request: ApiRequest(url: '${baseUrl}v1/first-value/recovery/pendant-connection', method: 'POST'),
        decode: _recordedPendantConnection,
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
}
