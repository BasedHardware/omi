import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/budget_choice_wire.g.dart';
import 'package:omi/env/env.dart';

/// A month rollover returns 409 budget_period_changed. The dialog reloads and asks again.
bool budgetPeriodChanged(ApiResult<dynamic> result) =>
    result is ApiFailure && result.problem.statusCode == 409 && result.problem.detail == 'budget_period_changed';

/// A choice records intent; it never grants cloud processing or consumes held audio.
class BudgetChoiceApi {
  BudgetChoiceApi({String? baseUrl, this.send}) : baseUrl = baseUrl ?? Env.apiBaseUrl ?? '';
  final String baseUrl;
  final ApiSend? send;
  static const capability = {'X-Omi-Held-Content': '1'};

  Future<ApiResult<GeneratedBudgetChoiceResponse>> load() => executeApi(
        request: ApiRequest(url: '${baseUrl}v1/users/budget-choice', method: 'GET', headers: capability),
        decode: (body) => GeneratedBudgetChoiceResponse.fromJson(jsonDecode(body) as Map<String, dynamic>),
        send: send,
      );

  Future<ApiResult<GeneratedBudgetChoiceWriteResponse>> save(String period, String choice, bool dontAskAgain) =>
      executeApi(
        request: ApiRequest(
          url: '${baseUrl}v1/users/budget-choice',
          method: 'PUT',
          headers: capability,
          body: jsonEncode({'period': period, 'choice': choice, 'dont_ask_again': dontAskAgain}),
        ),
        decode: (body) => GeneratedBudgetChoiceWriteResponse.fromJson(jsonDecode(body) as Map<String, dynamic>),
        send: send,
      );
}
