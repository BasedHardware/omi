import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/first_value.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/first_value_recovery_service.dart';
import 'package:omi/services/notifications.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('off response and both server-owned prompt routes decode closed', () {
    expect(FirstValueResponse.fromResponse('{"prompt":null}').prompt, isNull);
    expect(FirstValueResponse.fromResponse('{"prompt":{"kind":"capture","route":"/settings/device"}}').prompt?.route,
        '/settings/device');
    expect(
        FirstValueResponse.fromResponse('{"prompt":{"kind":"result","route":"/conversation/result-1"}}').prompt?.route,
        '/conversation/result-1');
    expect(() => FirstValueResponse.fromResponse('{"prompt":{"kind":"result","route":"https://elsewhere.invalid"}}'),
        throwsFormatException);
    expect(() => FirstValueResponse.fromResponse('{"prompt":{"kind":"other","route":"/settings/device"}}'),
        throwsFormatException);
    expect(() => FirstValueResponse.fromResponse('[]'), throwsFormatException);
    expect(() => FirstValueResponse.fromResponse('{broken'), throwsFormatException);
  });

  test('ready navigation authenticates the prompt instead of reading an FCM object id', () async {
    late ApiRequest observed;
    final api = FirstValueApi(
      baseUrl: 'https://fixture.invalid/',
      send: (request) async {
        observed = request;
        expect(request.body, isEmpty);
        return http.Response(
            jsonEncode({
              'prompt': {'kind': 'result', 'channel': 'push_navigation', 'route': '/conversation/result-1'},
            }),
            200);
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
    expect(Uri.parse(observed.url).queryParameters, {'navigation': 'true', 'kind': 'result'});
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
