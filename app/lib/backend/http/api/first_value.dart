/// Owns the authenticated EXP-005 wire client and its optional prompt envelope.
/// Accepts only server-issued local recovery routes; failures stay typed.
library;

import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class FirstValuePrompt {
  const FirstValuePrompt({required this.kind, required this.route});

  final String kind;
  final String route;
}

/// A valid empty prompt is data inside a successful envelope, never an HTTP failure.
class FirstValueResponse {
  const FirstValueResponse({this.prompt});
  final FirstValuePrompt? prompt;

  static FirstValueResponse fromResponse(String body) {
    final decoded = jsonDecode(body) as Map<String, dynamic>;
    if (!decoded.containsKey('prompt')) throw const FormatException('missing first-value prompt');
    final prompt = decoded['prompt'];
    if (prompt == null) return const FirstValueResponse();
    if (prompt is! Map<String, dynamic>) throw const FormatException('invalid first-value prompt');
    final kind = prompt['kind'];
    final route = prompt['route'];
    if ((kind != 'capture' && kind != 'result') || route is! String || route.isEmpty) {
      throw const FormatException('invalid first-value prompt');
    }
    if (kind == 'capture' && route != '/settings/device') throw const FormatException('invalid capture route');
    if (kind == 'result' && !route.startsWith('/conversation/')) throw const FormatException('invalid result route');
    return FirstValueResponse(prompt: FirstValuePrompt(kind: kind, route: route));
  }
}

class FirstValueApi {
  FirstValueApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';

  static const protocolHeader = 'X-Omi-First-Value-Protocol';
  static const permissionHeader = 'X-Omi-Notification-Permission';
  static const timeZoneHeader = 'X-Omi-Time-Zone';

  final String baseUrl;
  final ApiSend? send;

  Future<ApiResult<FirstValueResponse>> prompt({
    bool navigation = false,
    String? notificationPermission,
    String? timeZone,
  }) =>
      executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/prompt${navigation ? '?navigation=true&kind=result' : ''}',
          method: 'GET',
          headers: {
            protocolHeader: '1',
            if (notificationPermission != null) permissionHeader: notificationPermission,
            if (timeZone != null) timeZoneHeader: timeZone,
          },
        ),
        decode: FirstValueResponse.fromResponse,
        send: send,
      ).timeout(
        const Duration(seconds: 15),
        onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      );

  Future<ApiResult<bool>> recordResultOpen(String conversationId) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/result-open',
          method: 'POST',
          headers: const {protocolHeader: '1'},
          body: jsonEncode({'conversation_id': conversationId}),
        ),
        decode: (body) => (((jsonDecode(body) as Map<String, dynamic>)['recorded'] as num?) ?? 0) > 0,
        send: send,
      ).timeout(
        const Duration(seconds: 15),
        onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      );

  Future<ApiResult<bool>> recordPendantConnection({
    String? notificationPermission,
    String? timeZone,
  }) =>
      executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/first-value/recovery/pendant-connection',
          method: 'POST',
          headers: {
            protocolHeader: '1',
            if (notificationPermission != null) permissionHeader: notificationPermission,
            if (timeZone != null) timeZoneHeader: timeZone,
          },
        ),
        decode: (body) => (jsonDecode(body) as Map<String, dynamic>)['recorded'] == true,
        send: send,
      ).timeout(
        const Duration(seconds: 15),
        onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      );
}
