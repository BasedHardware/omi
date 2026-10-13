import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/plan_storefront.dart';

/// W5 integration seam. No fixture fallback, client prices or alternate purchase rail.
/// All endpoint/field mapping belongs here when W5's contract lands.
class PlanStorefrontApi {
  PlanStorefrontApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';
  final String baseUrl;
  final ApiSend? send;

  Future<ApiResult<PlanStorefront>> load({required String source, required String locale}) => executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/payments/plan-presentation?${Uri(queryParameters: {
                'source': source,
                'locale': locale
              }).query}',
          method: 'GET',
        ),
        decode: (body) => PlanStorefront.fromJson(jsonDecode(body) as Map<String, dynamic>),
        send: send,
      ).timeout(const Duration(seconds: 15), onTimeout: () => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
}
