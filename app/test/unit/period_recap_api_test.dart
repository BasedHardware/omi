import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/recaps.dart';
import 'package:omi/backend/http/api_result.dart';

const _recapJson = {
  'period': 'week',
  'start_date': '2026-09-28',
  'end_date': '2026-10-04',
  'days_recorded': 3,
  'stats': {'total_conversations': 10, 'total_duration_minutes': 180},
  'busiest_day': {'date': '2026-10-01', 'total_conversations': 6, 'total_duration_minutes': 120},
  'top_people': [
    {'person_id': 'p-sam', 'name': 'Sam', 'conversations': 4, 'talk_minutes': 25},
  ],
  'previous': {'total_conversations': 5, 'total_duration_minutes': 100},
};

void main() {
  group('periodRecapUrl', () {
    test('names the period and the anchor date', () {
      final url = Uri.parse(periodRecapUrl('https://api.omi.me/', RecapPeriod.month, date: DateTime(2026, 10, 7)));

      expect(url.path, '/v1/users/recaps/month');
      expect(url.queryParameters, {'date': '2026-10-07'});
    });

    test('leaves the date to the server, which uses today in the user timezone', () {
      final url = Uri.parse(periodRecapUrl('https://api.omi.me/', RecapPeriod.week));

      expect(url.path, '/v1/users/recaps/week');
      expect(url.queryParameters, isEmpty);
    });
  });

  group('getPeriodRecap', () {
    test('decodes a recap', () async {
      ApiRequest? sent;
      final result = await getPeriodRecap(
        RecapPeriod.week,
        baseUrl: 'https://api.omi.me/',
        send: (request) async {
          sent = request;
          return http.Response(jsonEncode(_recapJson), 200);
        },
      );

      expect(sent!.method, 'GET');
      expect(sent!.url, endsWith('v1/users/recaps/week'));
      final recap = (result as ApiSuccess).data;
      expect(recap.stats!.totalConversations, 10);
      expect(recap.busiestDay!.date, '2026-10-01');
      expect(recap.topPeople!.single.name, 'Sam');
      expect(recap.previous!.totalConversations, 5);
    });

    test('a server error is a failure, never an empty recap', () async {
      final result = await getPeriodRecap(
        RecapPeriod.week,
        baseUrl: 'https://api.omi.me/',
        send: (_) async => http.Response('oops', 503),
      );

      expect((result as ApiFailure).problem.kind, ApiProblemKind.server);
    });

    test('a body that is not a recap is a decode failure', () async {
      final result = await getPeriodRecap(
        RecapPeriod.week,
        baseUrl: 'https://api.omi.me/',
        send: (_) async => http.Response('[]', 200),
      );

      expect((result as ApiFailure).problem.kind, ApiProblemKind.decode);
    });
  });
}
