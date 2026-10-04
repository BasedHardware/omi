import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  const messagesUrl = 'http://127.0.0.1:9/v2/messages';

  setUpAll(() async {
    Env.init(const _EnvFields());
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  http.StreamedResponse sse(List<String> frames, {int status = 200}) {
    final body = frames.map((f) => '$f\n\n').join();
    return http.StreamedResponse(Stream.value(utf8.encode(body)), status);
  }

  ApiStreamingSeams seams(
    Future<http.StreamedResponse> Function(http.BaseRequest request) transport, {
    AuthService? auth,
    Future<Map<String, String>> Function()? headers,
  }) {
    return ApiStreamingSeams(
      transport: transport,
      headers: (request) async => await headers?.call() ?? const <String, String>{'Authorization': 'Bearer token'},
      auth: auth,
    );
  }

  test('401 then refreshed replay delivers the response frames', () async {
    final service = AuthService.forTesting(tokenGateway: _Gateway(), refreshDelay: (_) async {});
    var sends = 0;
    final chunks = await makeStreamingApiCall(
      url: messagesUrl,
      seams: seams((request) async {
        sends++;
        return sends == 1 ? sse(const [], status: 401) : sse(const ['data: hello', 'done: e30=']);
      }, auth: service),
    ).toList();

    expect(sends, 2);
    expect(chunks, ['data: hello', 'done: e30=']);
  });

  test('a final 401 after refresh is a notSignedIn failure', () async {
    final service = AuthService.forTesting(tokenGateway: _Gateway(), refreshDelay: (_) async {});
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => sse(const [], status: 401), auth: service),
      ).toList(),
      throwsA(
        isA<ChatStreamException>()
            .having((e) => e.kind, 'kind', ChatStreamFailureClass.notSignedIn)
            .having((e) => e.statusCode, 'statusCode', 401),
      ),
    );
  });

  test('a 401 with a transient refresh failure is offline: one send, no session expiry', () async {
    fakeAsync((async) {
      final service = AuthService.forTesting(
        tokenGateway: _Gateway(transient: true),
        refreshDelay: (_) async {},
      );
      final expired = <AuthSessionExpiredEvent>[];
      final sub = service.sessionExpiredEvents.listen(expired.add);
      addTearDown(sub.cancel);

      var sends = 0;
      Object? error;
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async {
          sends++;
          return sse(const [], status: 401);
        }, auth: service),
      ).listen((_) {}, onError: (e) => error = e);
      async.flushTimers();
      async.flushMicrotasks();

      expect(sends, 1);
      expect(error, isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.offline));
      expect(expired, isEmpty);
    });
  });

  test('a 503 is a classified server failure with its status', () async {
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => sse(const [], status: 503)),
      ).toList(),
      throwsA(
        isA<ChatStreamException>()
            .having((e) => e.kind, 'kind', ChatStreamFailureClass.server)
            .having((e) => e.statusCode, 'statusCode', 503),
      ),
    );
  });

  test('a stalled error body hits the setup bound instead of hanging', () async {
    Object? error;
    fakeAsync((async) {
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(StreamController<List<int>>().stream, 503)),
      ).listen((_) {}, onError: (e) => error = e);
      async.elapse(const Duration(seconds: 130));
    });
    await pumpEventQueue();

    expect(error, isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.timeout));
  });

  test('an early body disconnect still reports the HTTP status', () async {
    final cut = Stream<List<int>>.error(const SocketException('reset'));
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(cut, 503)),
      ).toList(),
      throwsA(
        isA<ChatStreamException>()
            .having((e) => e.kind, 'kind', ChatStreamFailureClass.server)
            .having((e) => e.statusCode, 'statusCode', 503),
      ),
    );
  });

  test('402 keeps its legacy quota frame instead of throwing', () async {
    final chunks = await makeStreamingApiCall(
      url: messagesUrl,
      seams: seams((request) async => sse(const [], status: 402)),
    ).toList();

    expect(chunks, hasLength(1));
    expect(chunks.single, startsWith('error:402:'));
  });

  test('402 surfaces to the chat parser as a quota_exceeded error chunk even with a bad body', () async {
    for (final body in ['{}', 'not-json']) {
      final chunks = await sendMessageStreamServer(
        'hi',
        seams: seams((request) async => http.StreamedResponse(Stream.value(utf8.encode(body)), 402)),
      ).toList();

      expect(chunks, hasLength(1), reason: body);
      expect(chunks.single.type, MessageChunkType.error);
      expect(chunks.single.errorCode, 'quota_exceeded');
    }
  });

  test('sendMessageStreamServer opts into the typed chat failure protocol header', () async {
    Map<String, String>? sentHeaders;
    await sendMessageStreamServer(
      'hi',
      seams: ApiStreamingSeams(
        transport: (request) async {
          sentHeaders = request.headers;
          return sse(const []);
        },
        headers: (request) async => <String, String>{'Authorization': 'Bearer token', ...request.headers},
      ),
    ).toList();

    expect(sentHeaders?['X-Omi-Chat-Failure-Protocol'], '1');
  });

  test('heartbeat comments reach the parser as no frames before done', () async {
    final chunks = await sendMessageStreamServer(
      'hi',
      seams: seams((request) async => http.StreamedResponse(Stream.value(utf8.encode(': hb\n\n\n\n')), 200)),
    ).toList();

    expect(chunks, isEmpty);
  });

  test('a socket failure is classified offline', () async {
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => throw const SocketException('no route')),
      ).toList(),
      throwsA(isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.offline)),
    );
  });

  test('an idle gap between frames is classified timeout', () async {
    Object? error;
    fakeAsync((async) {
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(StreamController<List<int>>().stream, 200)),
      ).listen((_) {}, onError: (e) => error = e);
      async.elapse(const Duration(seconds: 130));
    });
    await pumpEventQueue();

    expect(error, isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.timeout));
  });

  test('heartbeat comments under the total budget keep a long stream alive', () async {
    final chunks = <String>[];
    Object? error;
    fakeAsync((async) {
      final controller = StreamController<List<int>>();
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(controller.stream, 200)),
      ).listen(chunks.add, onError: (e) => error = e);

      for (var i = 0; i < 8; i++) {
        controller.add(utf8.encode(': hb\n\n'));
        async.elapse(const Duration(seconds: 20));
      }
      controller.add(utf8.encode('data: tail\n\n'));
      async.flushMicrotasks();
    });
    await pumpEventQueue();

    expect(error, isNull);
    expect(chunks.last, 'data: tail');
    expect(chunks.length, 9);
  });

  test('the stream terminates cleanly when the body closes', () async {
    final controller = StreamController<List<int>>();
    final expectation = expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(controller.stream, 200)),
      ),
      emitsInOrder([': hb', 'data: tail', emitsDone]),
    );
    controller.add(utf8.encode(': hb\n\n'));
    await pumpEventQueue();
    controller.add(utf8.encode('data: tail\n\n'));
    await pumpEventQueue();
    await controller.close();
    await expectation.timeout(const Duration(seconds: 5));
  });

  test('the stream total bound trips even while frames keep arriving', () async {
    Object? error;
    fakeAsync((async) {
      final controller = StreamController<List<int>>();
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams((request) async => http.StreamedResponse(controller.stream, 200)),
      ).listen((_) {}, onError: (e) => error = e);

      for (var i = 0; i < 25; i++) {
        controller.add(utf8.encode(': hb\n\n'));
        async.elapse(const Duration(seconds: 10));
      }
    });
    await pumpEventQueue();

    expect(error, isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.timeout));
  });

  test('a terminal auth failure before send is notSignedIn', () async {
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams(
          (request) async => sse(const ['data: hi']),
          headers: () async => throw AuthTokenUnavailableException(const AuthTokenMissingUser()),
        ),
      ).toList(),
      throwsA(isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.notSignedIn)),
    );
  });

  test('a transient auth failure before send is offline, never sign-out', () async {
    await expectLater(
      makeStreamingApiCall(
        url: messagesUrl,
        seams: seams(
          (request) async => sse(const ['data: hi']),
          headers: () async =>
              throw AuthTokenUnavailableException(const AuthTokenTransientFailure(failureClass: 'network')),
        ),
      ).toList(),
      throwsA(isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.offline)),
    );
  });

  test('multipart streaming surfaces the same classified failures', () async {
    final file = File('${Directory.systemTemp.path}/omi-chat-stream-test.txt');
    await file.writeAsString('test');
    addTearDown(() => file.delete().ignore());

    await expectLater(
      makeMultipartStreamingApiCall(
        url: '${Env.apiBaseUrl}v2/voice-messages',
        files: [file],
        seams: seams((request) async => sse(const [], status: 500)),
      ).toList(),
      throwsA(
        isA<ChatStreamException>()
            .having((e) => e.kind, 'kind', ChatStreamFailureClass.server)
            .having((e) => e.statusCode, 'statusCode', 500),
      ),
    );
  });
}

final class _Gateway implements AuthTokenGateway {
  _Gateway({this.transient = false});

  final bool transient;

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'test-user');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    if (transient) throw StateError('transient network failure');
    return RefreshedAuthToken(token: 'fresh-token', expirationTime: DateTime.now().add(const Duration(hours: 1)));
  }

  @override
  Future<void> signOut() async {}
}

final class _EnvFields implements EnvFields {
  const _EnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
