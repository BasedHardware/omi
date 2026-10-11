import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<void> syncUserTimeZoneServer({required String timeZone}) async {
  await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/time-zone',
    headers: {},
    method: 'PUT',
    body: jsonEncode({'time_zone': timeZone}),
  );
}

Future<void> saveFcmTokenServer({required String token, required String timeZone}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/users/fcm-token',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode({'fcm_token': token, 'time_zone': timeZone}),
  );

  Logger.debug('saveToken: ${response?.body}');
  if (response?.statusCode == 200) {
    final data = wire.GeneratedFcmTokenResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
    Logger.debug(data.status == 'Ok' ? "Token saved successfully" : "Token save returned ${data.status}");
  } else {
    Logger.debug("Failed to save token");
  }
}

/// Shared server feed; callers retain item IDs when reporting confirmed actions.
class ProactivityApi {
  ProactivityApi({this.send, String? baseUrl}) : _baseUrl = baseUrl;

  final ApiSend? send;
  final String? _baseUrl;

  String _url(String path, [Map<String, String> query = const {}]) =>
      Uri.parse('${_baseUrl ?? Env.apiBaseUrl}$path').replace(queryParameters: query.isEmpty ? null : query).toString();

  Future<ApiResult<GeneratedProactivityFeedResponse>> feed({int limit = 20, String cursor = ''}) => executeApi(
        request: ApiRequest(url: _url('v1/proactivity/feed', {'limit': '$limit', 'cursor': cursor}), method: 'GET'),
        send: send,
        decode: (body) {
          final value = jsonDecode(body);
          if (value is! Map<String, dynamic>) throw const FormatException('Invalid proactivity feed');
          return GeneratedProactivityFeedResponse.fromJson(value);
        },
      );

  Future<ApiResult<GeneratedProactivityOutcomeResponse>> outcome(
    String itemId,
    GeneratedProactivityOutcomeRequest event,
  ) =>
      executeApi(
        request: ApiRequest(
          url: _url('v1/proactivity/items/${Uri.encodeComponent(itemId)}/outcomes'),
          method: 'POST',
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode(event.toJson()),
        ),
        send: send,
        decode: (body) {
          final value = jsonDecode(body);
          if (value is! Map<String, dynamic>) throw const FormatException('Invalid proactivity outcome');
          return GeneratedProactivityOutcomeResponse.fromJson(value);
        },
      );
}
