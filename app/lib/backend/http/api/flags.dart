import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/flags_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Flags owned by Omi's flag store for the signed-in account. Keys the store does not list keep reading PostHog.
class OmiFlagsApi {
  const OmiFlagsApi({this.send});

  final ApiSend? send;

  Future<ApiResult<List<wire.GeneratedClientFlag>>> getClientFlags() => executeApi(
        request: ApiRequest(url: '${Env.apiBaseUrl}v1/flags?surface=mobile', method: 'GET'),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('invalid flags response');
          return wire.GeneratedClientFlagsResponse.fromJson(row).flags;
        },
      );
}
