import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/models/plan_storefront.dart';

void main() {
  for (final trigger in ['', 'usage_budget', 'proactive_agent', 'screen_context', 'mcp_daily_cap']) {
    test('storefront sends only declared context: $trigger', () async {
      ApiRequest? seen;
      final api = PlanStorefrontApi(
          baseUrl: 'http://localhost/',
          send: (request) async {
            seen = request;
            return http.Response(File('test/fixtures/storefront_v2/pro_budget80.json').readAsStringSync(), 200);
          });
      expect(await api.load(source: 'budget_80', trigger: trigger, locale: 'en'), isA<ApiSuccess<PlanStorefront>>());
      final parameters = Uri.parse(seen!.url).queryParameters;
      expect(parameters['trigger'], trigger.isEmpty ? null : trigger);
      expect(parameters['source'], 'budget_80');
    });
  }
}
