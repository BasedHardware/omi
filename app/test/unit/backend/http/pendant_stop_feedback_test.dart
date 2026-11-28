import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/http/shared.dart' show AuthTokenUnavailableException;
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

class _AuthStub implements AuthService {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'survey-user'});
    await SharedPreferencesUtil.init();
    Env.overrideApiBaseUrl('https://example.test/');
    addTearDown(Env.clearApiBaseUrlOverride);
  });

  test('sends each typed reason through the authenticated feedback POST', () async {
    final requests = <ApiRequest>[];
    final execution = ApiExecutionSeams(
      auth: _AuthStub(),
      headers: (_) async => {'Authorization': 'Bearer test-token'},
      transport: (request) async {
        requests.add(request);
        return http.Response('', 204);
      },
    );

    for (final reason in PendantStopQuestionAnsweredReason.values) {
      await submitPendantStopFeedback('survey-user', reason, 'Private note', 4, execution: execution);
    }

    expect(
      requests.map((request) => (jsonDecode(request.body) as Map)['reason']),
      [
        'uncomfortable_to_wear',
        'forgot_or_no_habit',
        'charging_is_a_hassle',
        'not_useful_enough',
        'device_problem',
        'other',
        'note_only',
      ],
    );
    for (final request in requests) {
      expect(request.method, 'POST');
      expect(request.url, 'https://example.test/v1/users/pendant-stop-feedback');
      expect(request.headers['Authorization'], 'Bearer test-token');
      expect(jsonDecode(request.body), {
        'reason': isA<String>(),
        'details': 'Private note',
        'days_without_connection': 4,
      });
    }
  });

  test('drops a private note when the account changes during header resolution', () async {
    final execution = ApiExecutionSeams(
      auth: _AuthStub(),
      headers: (_) async {
        SharedPreferencesUtil().uid = 'other-user';
        return {};
      },
      transport: (_) async => throw StateError('A stale note reached the transport'),
    );

    await expectLater(
      submitPendantStopFeedback('survey-user', PendantStopQuestionAnsweredReason.noteOnly, 'Private note', 4,
          execution: execution),
      throwsA(isA<AuthTokenUnavailableException>()),
    );
  });
}
