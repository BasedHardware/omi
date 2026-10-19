import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/plan_storefront.dart';

/// Reads the v2 plans presentation. No fixture fallback, client prices, or alternate purchase rail.
class PlanStorefrontApi {
  PlanStorefrontApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';
  final String baseUrl;
  final ApiSend? send;

  Future<ApiResult<PlanStorefront>> load({
    required String source,
    String trigger = '',
    required String locale,
  }) =>
      executeApi(
        request: ApiRequest(
          url: '${baseUrl}v2/payments/plans?${Uri(queryParameters: {
                'source': source,
                if (trigger.isNotEmpty) 'trigger': trigger,
                'locale': locale,
              }).query}',
          method: 'GET',
        ),
        decode: (body) => PlanStorefront.fromJson(jsonDecode(body) as Map<String, dynamic>),
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
}
