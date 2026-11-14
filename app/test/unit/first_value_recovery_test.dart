import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/first_value.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/first_value_recovery_service.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('off response and both server-owned prompt routes decode closed', () {
    expect(FirstValueResponse.fromResponse('{"prompt":null}').prompt, isNull);
    expect(
      FirstValueResponse.fromResponse(
        '{"prompt":{"kind":"capture","route":"/settings/device"}}',
      ).prompt?.route,
      '/settings/device',
    );
    expect(
      FirstValueResponse.fromResponse(
        '{"prompt":{"kind":"result","route":"/conversation/result-1"}}',
      ).prompt?.route,
      '/conversation/result-1',
    );
    expect(
      () => FirstValueResponse.fromResponse(
        '{"prompt":{"kind":"result","route":"https://elsewhere.invalid"}}',
      ),
      throwsFormatException,
    );
    expect(
      () => FirstValueResponse.fromResponse(
        '{"prompt":{"kind":"other","route":"/settings/device"}}',
      ),
      throwsFormatException,
    );
  });

  test('valid empty response stays distinct from transport and decode failures', () async {
    Future<ApiResult<FirstValueResponse>> response(int status, String body) => FirstValueApi(
          baseUrl: 'https://fixture.invalid/',
          send: (_) async => http.Response(body, status),
        ).prompt();
    final empty = await response(200, '{"prompt":null}');
    expect(empty, isA<ApiSuccess<FirstValueResponse>>());
    expect((empty as ApiSuccess<FirstValueResponse>).data.prompt, isNull);
    expect(await response(500, '{}'), isA<ApiFailure<FirstValueResponse>>());
    expect(await response(200, '{}'), isA<ApiFailure<FirstValueResponse>>());
  });

  test('readiness requires an explicit boolean on the distinct nonclaiming route', () async {
    for (final fixture in [
      (200, '{"ready":false}', false),
      (200, '{"ready":true}', true),
      (404, '{}', null),
      (500, '{}', null),
      (200, '{}', null),
      (200, '{"ready":"true"}', null),
      (200, 'null', null),
      (200, '[]', null),
    ]) {
      final result = await FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (request) async {
          expect(Uri.parse(request.url).path, '/v1/first-value/recovery/prepare');
          expect(Uri.parse(request.url).query, isEmpty);
          expect(request.headers[FirstValueApi.protocolHeader], '1');
          return http.Response(fixture.$2, fixture.$1);
        },
      ).prepare();
      if (fixture.$3 == null) {
        expect(result, isA<ApiFailure<FirstValuePreparation>>());
      } else {
        expect((result as ApiSuccess<FirstValuePreparation>).data.ready, fixture.$3);
      }
    }
  });

  test(
    'ready navigation authenticates the prompt instead of reading an FCM object id',
    () async {
      AnalyticsManager.resetForTesting();
      AnalyticsManager().bindIdentity('synthetic-owner');
      addTearDown(AnalyticsManager.resetForTesting);
      late ApiRequest observed;
      final api = FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (request) async {
          observed = request;
          expect(request.body, isEmpty);
          expect(request.headers[FirstValueApi.protocolHeader], '1');
          return http.Response(
            jsonEncode({
              'prompt': {
                'kind': 'result',
                'channel': 'push_navigation',
                'route': '/conversation/result-1',
              },
            }),
            200,
          );
        },
      );
      final opened = <String>[];
      Future<bool> opener(String route, {bool Function()? canOpen}) async {
        opened.add(route);
        return true;
      }

      HomeNavigation.register(opener);
      addTearDown(() => HomeNavigation.unregister(opener));
      FirstValueRecoveryService.instance.debugApi = api;

      final handled = await NotificationUtil.handleFcmDataTap(const {
        'notification_type': 'first_value_ready_result',
        'action': 'open_ready_result',
        // The client never uses this spoofable target as its destination.
        'target_id': 'attacker-controlled',
        'navigate_to': '/conversations',
      });

      expect(handled, isTrue);
      expect(opened, ['/conversation/result-1']);
      expect(Uri.parse(observed.url).queryParameters, {
        'navigation': 'true',
        'kind': 'result',
      });
    },
  );

  test('unknown or signed-out identity cannot consume a prompt', () async {
    AnalyticsManager.resetForTesting();
    addTearDown(AnalyticsManager.resetForTesting);
    var requests = 0;
    FirstValueRecoveryService.instance.debugApi = FirstValueApi(
        baseUrl: 'https://fixture.invalid/',
        send: (_) async {
          requests++;
          return http.Response('{"prompt":null}', 200);
        });
    await FirstValueRecoveryService.instance.checkOnAppOpen();
    AnalyticsManager().bindIdentity(null);
    await FirstValueRecoveryService.instance.checkOnAppOpen();
    expect(requests, 0);
  });

  test('released generic route remains available for a ready notification', () {
    expect(
      NotificationUtil.routeFromFcmData(const {
        'notification_type': 'first_value_ready_result',
        'action': 'open_ready_result',
        'navigate_to': '/conversations',
      }),
      '/conversations',
    );
  });
}
