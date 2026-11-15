// Owns the optional yearly-retention admission/config transport.
// Preserve typed HTTP failures; only UI callers decide to hide an optional offer.
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

Future<ApiResult<wire.GeneratedYearlySwitchResponse>> claimYearlyRetention(String placement, {ApiSend? send}) {
  if (!const {'cancel', 'engaged'}.contains(placement)) throw ArgumentError.value(placement, 'placement');
  return executeApi(
    request:
        ApiRequest(url: '${Env.apiBaseUrl}v1/payments/yearly-switch-retention?placement=$placement', method: 'POST'),
    send: send,
    decode: (body) => wire.GeneratedYearlySwitchResponse.fromJson(jsonDecode(body) as Map<String, dynamic>),
  );
}

Future<ApiResult<bool>> yearlyRetentionStatus({ApiSend? send}) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/payments/yearly-switch-retention', method: 'GET'),
      send: send,
      decode: (body) => wire.GeneratedYearlySwitchResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).eligible,
    );
