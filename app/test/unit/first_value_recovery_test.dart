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
    expect(FirstValuePrompt.fromResponse('{"prompt":null}'), isNull);
    expect(
      FirstValuePrompt.fromResponse(
        '{"prompt":{"kind":"capture","route":"/settings/device"}}',
      )?.route,
      '/settings/device',
    );
    expect(
      FirstValuePrompt.fromResponse(
        '{"prompt":{"kind":"result","route":"/conversation/result-1"}}',
      )?.route,
      '/conversation/result-1',
    );
    expect(
      () => FirstValuePrompt.fromResponse(
        '{"prompt":{"kind":"result","route":"https://elsewhere.invalid"}}',
      ),
      throwsFormatException,
    );
    expect(
      () => FirstValuePrompt.fromResponse(
        '{"prompt":{"kind":"other","route":"/settings/device"}}',
      ),
      throwsFormatException,
    );
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
