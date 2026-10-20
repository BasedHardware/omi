import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/budget_choice_api.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/budget_choice_wire.g.dart';

void main() {
  test('choice uses the capability and backend period, and only saves intent', () async {
    final requests = <ApiRequest>[];
    final api = BudgetChoiceApi(
        baseUrl: 'http://localhost/',
        send: (request) async {
          requests.add(request);
          if (request.method == 'GET') {
            return http.Response(
                jsonEncode({'period': '2026-10', 'state': 'held_pending_choice', 'choice': null, 'ask': true}), 200);
          }
          return http.Response(
              jsonEncode({'period': '2026-10', 'ask': false, 'choice': jsonDecode(request.body)}), 200);
        });
    final result = await api.load();
    expect(result, isA<ApiSuccess<GeneratedBudgetChoiceResponse>>());
    final record = (result as ApiSuccess<GeneratedBudgetChoiceResponse>).data;
    expect(record.state, 'held_pending_choice');
    final saved = await api.save(record.period, 'on_device', true);
    expect(saved, isA<ApiSuccess<GeneratedBudgetChoiceWriteResponse>>());
    expect(requests.every((request) => request.headers['X-Omi-Held-Content'] == '1'), true);
    expect(jsonDecode(requests.last.body), {'period': '2026-10', 'choice': 'on_device', 'dont_ask_again': true});
  });
  test('disabled or changed-period response fails without fabricating a choice', () async {
    final api = BudgetChoiceApi(baseUrl: 'http://localhost/', send: (_) async => http.Response('{}', 409));
    final saved = await api.save('old', 'upgrade', false);
    expect(saved, isA<ApiFailure<GeneratedBudgetChoiceWriteResponse>>());
    expect(budgetPeriodChanged(saved), isFalse);
  });

  test('budget_period_changed is a bounded detail the dialog can reload', () async {
    final api = BudgetChoiceApi(
      baseUrl: 'http://localhost/',
      send: (_) async => http.Response(jsonEncode({'detail': 'budget_period_changed'}), 409),
    );
    final saved = await api.save('2026-10', 'on_device', false);
    expect(budgetPeriodChanged(saved), isTrue);
    final noisy = BudgetChoiceApi(
      baseUrl: 'http://localhost/',
      send: (_) async => http.Response(jsonEncode({'detail': 'user private text'}), 409),
    );
    expect(budgetPeriodChanged(await noisy.save('2026-10', 'on_device', false)), isFalse);
  });
}
