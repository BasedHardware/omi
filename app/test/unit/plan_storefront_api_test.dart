import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/plan_storefront_api.dart';
import 'package:omi/models/plan_storefront.dart';

void main() {
  test('one adapter forwards source, trigger and locale and preserves exact price ids', () async {
    final api = PlanStorefrontApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          final uri = Uri.parse(request.url);
          expect(uri.path, '/v2/payments/plans');
          expect(uri.queryParameters, {'source': 'proactive_agent_gate', 'trigger': 'proactive_agent', 'locale': 'vi'});
          expect(request.method, 'GET');
          return http.Response(File('test/fixtures/storefront_v2/settings.json').readAsStringSync(), 200);
        });
    final result = await api.load(source: 'proactive_agent_gate', trigger: 'proactive_agent', locale: 'vi');
    expect(
        (result as ApiSuccess<PlanStorefront>)
            .data
            .tiers
            .firstWhere((tier) => tier.planId == 'operator')
            .priceFor('year')!
            .id,
        'fixture_operator_year');
  });
  test('unavailable or incompatible backend has no synthetic fallback', () async {
    for (final response in [http.Response('{}', 404), http.Response('{"schema_version":1}', 200)]) {
      final api = PlanStorefrontApi(baseUrl: 'http://127.0.0.1:1/', send: (_) async => response);
      expect(
          await api.load(source: 'budget_80', trigger: 'budget_80', locale: 'en'), isA<ApiFailure<PlanStorefront>>());
    }
  });
}
