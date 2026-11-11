import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/assistant_voices.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'https://api.test/';
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

http.Response _json(int status, Object body) => http.Response(jsonEncode(body), status);

void main() {
  setUpAll(() {
    try {
      Env.init(_TestEnvFields());
    } catch (_) {}
  });

  group('AssistantVoicesApi decoding', () {
    test('catalog decodes voices and default id', () async {
      final api = AssistantVoicesApi(
        send: (request) async {
          expect(request.method, 'GET');
          expect(request.url, 'https://api.test/v1/tts/voices');
          return _json(200, {
            'voices': [
              {'id': 'Zephyr', 'name': 'Zephyr'},
              {'id': 'Charon', 'name': 'Charon'},
              {'id': 'Kore', 'name': 'Kore'},
            ],
            'default_voice_id': 'Charon',
          });
        },
      );
      final result = await api.getCatalog();
      expect(result, isA<ApiSuccess<AssistantVoiceCatalog>>());
      final catalog = (result as ApiSuccess<AssistantVoiceCatalog>).data;
      expect(catalog.voices.map((v) => v.id), ['Zephyr', 'Charon', 'Kore']);
      expect(catalog.voices.map((v) => v.name), ['Zephyr', 'Charon', 'Kore']);
      expect(catalog.defaultVoiceId, 'Charon');
    });

    test('duplicate ids dedupe last-wins without trapping', () async {
      final api = AssistantVoicesApi(
        send: (_) async => _json(200, {
          'voices': [
            {'id': 'Charon', 'name': 'Charon'},
            {'id': 'Kore', 'name': 'Kore'},
            {'id': 'Kore', 'name': 'Kore Alt'},
          ],
          'default_voice_id': 'Charon',
        }),
      );
      final result = await api.getCatalog();
      expect(result, isA<ApiSuccess<AssistantVoiceCatalog>>());
      final catalog = (result as ApiSuccess<AssistantVoiceCatalog>).data;
      expect(catalog.voices.map((v) => v.id), ['Charon', 'Kore']);
      expect(catalog.voices.last.name, 'Kore Alt');
    });

    test('empty catalog is a decode failure, not an empty picker', () async {
      final api = AssistantVoicesApi(
        send: (_) async => _json(200, {'voices': <dynamic>[], 'default_voice_id': 'Charon'}),
      );
      expect(await api.getCatalog(), isA<ApiFailure<AssistantVoiceCatalog>>());
    });

    test('a malformed voice row fails the whole catalog decode', () async {
      final api = AssistantVoicesApi(
        send: (_) async => _json(200, {
          'voices': [
            {'id': 'Charon', 'name': 'Charon'},
            'not-a-map',
          ],
          'default_voice_id': 'Charon',
        }),
      );
      expect(await api.getCatalog(), isA<ApiFailure<AssistantVoiceCatalog>>());
      final api2 = AssistantVoicesApi(
        send: (_) async => _json(200, {
          'voices': [
            {'id': 'Charon', 'name': 'Charon'},
            {'id': 'Kore'},
          ],
          'default_voice_id': 'Charon',
        }),
      );
      expect(await api2.getCatalog(), isA<ApiFailure<AssistantVoiceCatalog>>());
    });

    test('a default id absent from the catalog is a decode failure', () async {
      final api = AssistantVoicesApi(
        send: (_) async => _json(200, {
          'voices': [
            {'id': 'Kore', 'name': 'Kore'},
          ],
          'default_voice_id': 'Charon',
        }),
      );
      expect(await api.getCatalog(), isA<ApiFailure<AssistantVoiceCatalog>>());
    });

    test('getPreference decodes voice_id', () async {
      final api = AssistantVoicesApi(
        send: (request) async {
          expect(request.method, 'GET');
          expect(request.url, 'https://api.test/v1/users/voice');
          return _json(200, {'voice_id': 'Kore'});
        },
      );
      final result = await api.getPreference();
      expect((result as ApiSuccess<AssistantVoicePreference>).data.voiceId, 'Kore');
    });

    test('setPreference PATCHes voice_id and trusts the acked value', () async {
      final api = AssistantVoicesApi(
        send: (request) async {
          expect(request.method, 'PATCH');
          expect(request.url, 'https://api.test/v1/users/voice');
          expect(jsonDecode(request.body), {'voice_id': 'Puck'});
          return _json(200, {'voice_id': 'Charon'});
        },
      );
      final result = await api.setPreference('Puck');
      expect((result as ApiSuccess<AssistantVoicePreference>).data.voiceId, 'Charon');
    });

    test('malformed payloads are decode failures, not crashes', () async {
      final api = AssistantVoicesApi(send: (_) async => _json(200, {'voices': 'not-a-list'}));
      expect(await api.getCatalog(), isA<ApiFailure<AssistantVoiceCatalog>>());
      final api2 = AssistantVoicesApi(send: (_) async => _json(200, {'voice_id': ''}));
      expect(await api2.getPreference(), isA<ApiFailure<AssistantVoicePreference>>());
    });

    test('error statuses surface as failures', () async {
      final api = AssistantVoicesApi(send: (_) async => _json(503, {'error': 'down'}));
      final result = await api.getPreference();
      expect(result, isA<ApiFailure<AssistantVoicePreference>>());
      expect((result as ApiFailure<AssistantVoicePreference>).problem.retryable, isTrue);
    });
  });
}
