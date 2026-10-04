import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// A weekly (Monday-Sunday) or monthly recap, rolled up from the daily recaps.
enum RecapPeriod { week, month }

String periodRecapUrl(String baseUrl, RecapPeriod period, {DateTime? date}) {
  final root = baseUrl.endsWith('/') ? baseUrl : '$baseUrl/';
  final url = Uri.parse('${root}v1/users/recaps/${period.name}');
  if (date == null) return url.toString();
  final day = '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
  return url.replace(queryParameters: {'date': day}).toString();
}

/// The recap for the period containing [date] (today, in the user's timezone, by default).
Future<ApiResult<wire.GeneratedPeriodRecapResponse>> getPeriodRecap(
  RecapPeriod period, {
  DateTime? date,
  ApiSend? send,
  String? baseUrl,
}) =>
    executeApi<wire.GeneratedPeriodRecapResponse>(
      request: ApiRequest(url: periodRecapUrl(baseUrl ?? Env.apiBaseUrl ?? '', period, date: date), method: 'GET'),
      send: send,
      decode: (body) {
        final value = jsonDecode(body);
        if (value is! Map<String, dynamic>) throw const FormatException('Expected a recap object');
        return wire.GeneratedPeriodRecapResponse.fromJson(value);
      },
    );
