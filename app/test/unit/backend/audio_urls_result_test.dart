import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

class _UrlsEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://audio-urls.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUpAll(() {
    Env.init(_UrlsEnv());
  });

  group('getConversationAudioSignedUrls outcomes', () {
    test('a thrown transport error is a transport failure, never an empty success', () async {
      final result = await getConversationAudioSignedUrls(
        'conv-1',
        send: (_) async => throw const SocketException('unreachable'),
      );
      final problem = (result as ApiFailure<AudioUrlsResponse>).problem;
      expect(problem.kind, ApiProblemKind.transport);
    });

    test('a successful empty answer is success with no files, not a failure', () async {
      final result = await getConversationAudioSignedUrls(
        'conv-1',
        send: (_) async => http.Response('{"audio_files": []}', 200),
      );
      final data = (result as ApiSuccess<AudioUrlsResponse>).data;
      expect(data.files, isEmpty);
    });

    test('a 503 is a server failure carrying its status, not silence', () async {
      final result = await getConversationAudioSignedUrls(
        'conv-1',
        send: (_) async => http.Response('unavailable', 503),
      );
      final problem = (result as ApiFailure<AudioUrlsResponse>).problem;
      expect(problem.kind, ApiProblemKind.server);
      expect(problem.statusCode, 503);
    });

    test('a 200 with an undecodable body is a decode failure', () async {
      final result = await getConversationAudioSignedUrls('conv-1', send: (_) async => http.Response('not json', 200));
      expect((result as ApiFailure<AudioUrlsResponse>).problem.kind, ApiProblemKind.decode);
    });
  });
}
