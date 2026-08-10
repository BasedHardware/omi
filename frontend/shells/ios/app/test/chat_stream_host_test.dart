import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/bridge_http_host.dart';
import 'package:omi_webview_proto/chat_bridge_javascript_sink.dart';
import 'package:omi_webview_proto/chat_stream_host.dart';

import 'chat_native_test_fakes.dart';

String frame(Map<String, Object> value) => jsonEncode(value);

ChatStreamHost makeHost(FakeChatNativeHttpClient client, List<String> scripts, ShellCredentialCustody custody) {
  return ChatStreamHost(
    baseUrl: Uri.parse('https://service.example.test/base'),
    custody: custody,
    clientIdentity: 'run-stream::ios',
    sink: ChatBridgeJavaScriptSink((source) async => scripts.add(source)),
    httpClient: client,
  );
}

void main() {
  test('stateful UTF-8 streams every byte split through the real JS sink before terminal', () async {
    // red-proof: replace `response.bytes.transform(const Utf8Decoder())` with
    // per-chunk `utf8.decode`; the split multibyte payload errors before the
    // two deltas can reach the sink.
    final responseBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(
          statusCode: 200,
          contentType: 'Text/Event-Stream; Charset=UTF-8',
          bytes: responseBytes.stream,
        ),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, ShellCredentialCustody('native-secret'));
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-byte-split',
        'channel': 'chat-generation-events',
        'params': jsonEncode(<String, Object>{'generationId': 'generation/reconnect', 'lastEventId': 'event-exact-2'}),
        'credit': 1000,
      }),
    );
    await waitFor(() => client.requests.length == 1, reason: 'stream request');

    const sse =
        'id: event-1\nevent: delta\ndata: {"kind":"delta","text":"café"}\n\n'
        'id: event-2\nevent: delta\ndata: {"kind":"delta","text":" 🌍"}\n\n';
    for (final byte in utf8.encode(sse)) {
      responseBytes.add(<int>[byte]);
    }
    await responseBytes.close();
    await waitFor(
      () => scripts.map(parseSingleArgumentFrame).any((item) => item['t'] == 'end'),
      reason: 'terminal end frame',
    );

    final request = client.requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/v1/chat-generations/generation%2Freconnect/events');
    expect(request.followsRedirects, isFalse);
    expect(request.headers['last-event-id'], 'event-exact-2');
    expect(request.headers['authorization'], 'Bearer native-secret');
    expect(request.headers['x-omi-contract-version'], '1.0.0');
    expect(request.headers['x-omi-client-id'], 'run-stream::ios');

    final emitted = scripts.map(parseSingleArgumentFrame).toList(growable: false);
    final terminalIndex = emitted.indexWhere((item) => item['t'] == 'end');
    final payload = emitted
        .take(terminalIndex)
        .where((item) => item['t'] == 'data')
        .map((item) => item['payload'] as String)
        .join();
    expect(payload, sse);
    expect(payload.split('event: delta').length - 1, 2);
    expect(scripts.join(), isNot(contains('native-secret')));
    expect(scripts.join(), isNot(contains('service.example.test')));
    expect(emitted.where((item) => item['t'] == 'end'), hasLength(1));
    await host.close();
  });

  test('credit pauses delivery, grant resumes exactly its count, and cancel closes the socket', () async {
    // red-proof: delete `subscription.pause()` in `_ChatStreamSession.start`;
    // all three chunks reach the JS sink before the grant assertion.
    final responseBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: responseBytes.stream),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, ShellCredentialCustody('token'));
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-credit',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-credit"}',
        'credit': 1,
      }),
    );
    await waitFor(() => client.requests.length == 1);
    responseBytes
      ..add(utf8.encode('one'))
      ..add(utf8.encode('two'))
      ..add(utf8.encode('three'));
    await waitFor(
      () => scripts.map(parseSingleArgumentFrame).where((item) => item['t'] == 'data').length == 1,
      reason: 'one credited frame',
    );
    await Future<void>.delayed(Duration.zero);
    expect(scripts.map(parseSingleArgumentFrame).where((item) => item['t'] == 'data'), hasLength(1));

    await host.handleMessage(
      frame(<String, Object>{'t': 'grant', 'id': 's-credit', 'channel': 'chat-generation-events', 'credit': 2}),
    );
    await waitFor(
      () => scripts.map(parseSingleArgumentFrame).where((item) => item['t'] == 'data').length == 3,
      reason: 'two granted frames',
    );
    await host.handleMessage(
      frame(<String, Object>{
        't': 'cancel',
        'id': 's-credit',
        'channel': 'chat-generation-events',
        'reason': 'consumer-return',
      }),
    );
    expect(client.requests.single.aborted, isTrue);
    expect(host.activeSessionCount, 0);
    await responseBytes.close();
    await Future<void>.delayed(Duration.zero);
    expect(scripts.map(parseSingleArgumentFrame).where((item) => item['t'] == 'end'), isEmpty);
    await host.close();
  });

  test('duplicate malformed and wrong-channel frames cannot contaminate another session', () async {
    final firstBytes = StreamController<List<int>>();
    final secondBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: firstBytes.stream),
      )
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: secondBytes.stream),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, ShellCredentialCustody('token'));
    final firstOpen = <String, Object>{
      't': 'open',
      'id': 's-one',
      'channel': 'chat-generation-events',
      'params': '{"generationId":"generation-one"}',
      'credit': 1,
    };
    await host.handleMessage(frame(firstOpen));
    await waitFor(() => client.requests.length == 1);
    await host.handleMessage(frame(firstOpen));
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-wrong',
        'channel': 'listen-events',
        'params': '{"generationId":"generation-wrong"}',
        'credit': 1,
      }),
    );
    await host.handleMessage(
      frame(<String, Object>{
        't': 'grant',
        'id': 's-one',
        'channel': 'chat-generation-events',
        'credit': 1,
        'callerToken': 'must-be-refused',
      }),
    );
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-caller-metadata',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-safe","origin":"https://caller.invalid","token":"caller-token"}',
        'credit': 1,
      }),
    );
    expect(client.requests, hasLength(1));

    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-two',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-two"}',
        'credit': 1,
      }),
    );
    await waitFor(() => client.requests.length == 2);
    await host.handleMessage(
      frame(<String, Object>{'t': 'cancel', 'id': 's-one', 'channel': 'chat-generation-events'}),
    );
    expect(client.requests[0].aborted, isTrue);
    expect(client.requests[1].aborted, isFalse);
    expect(host.activeSessionCount, 1);
    expect(scripts.join(), isNot(contains('must-be-refused')));
    expect(scripts.join(), isNot(contains('caller.invalid')));
    expect(scripts.join(), isNot(contains('caller-token')));
    await host.close();
    await firstBytes.close();
    await secondBytes.close();
  });

  test('exact sign-out prevents a later Chat stream request before dispatch', () async {
    final custody = ShellCredentialCustody('token');
    custody.observeResponse(method: 'DELETE', path: '/v1/session/current', status: 204);
    final client = FakeChatNativeHttpClient();
    final scripts = <String>[];
    final host = makeHost(client, scripts, custody);
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-signed-out',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-signed-out"}',
        'credit': 1,
      }),
    );
    expect(client.requests, isEmpty);
    expect(parseSingleArgumentFrame(scripts.single)['failure'], 'not-authenticated');
    await host.close();
  });

  test('sign-out near misses retain authority for a new Chat open', () async {
    final custody = ShellCredentialCustody('token');
    custody.observeResponse(method: 'DELETE', path: '/v1/session/current', status: 503);
    final responseBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: responseBytes.stream),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, custody);
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-near-miss',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-near-miss"}',
        'credit': 1,
      }),
    );
    await waitFor(() => client.requests.length == 1);
    expect(client.requests.single.headers['authorization'], 'Bearer token');
    await host.close();
    await responseBytes.close();
  });

  test('an already opened Chat lease may finish after exact sign-out', () async {
    final custody = ShellCredentialCustody('token');
    final responseBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: responseBytes.stream),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, custody);
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-leased',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-leased"}',
        'credit': 2,
      }),
    );
    await waitFor(() => client.requests.length == 1);
    custody.observeResponse(method: 'DELETE', path: '/v1/session/current', status: 204);
    responseBytes.add(utf8.encode('leased-data'));
    await responseBytes.close();
    await waitFor(() => scripts.map(parseSingleArgumentFrame).any((frame) => frame['t'] == 'end'));
    expect(scripts.join(), contains('leased-data'));

    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-after-signout',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-after"}',
        'credit': 1,
      }),
    );
    expect(client.requests, hasLength(1));
    expect(scripts.join(), contains('not-authenticated'));
    await host.close();
  });

  test('generation stream refuses missing or wrong response media type', () async {
    for (final contentType in <String?>[null, 'application/json']) {
      final marker = 'body-must-not-reach-js';
      final client = FakeChatNativeHttpClient()
        ..responses.add(
          FakeChatNativeHttpResponse(
            statusCode: 200,
            contentType: contentType,
            bytes: Stream<List<int>>.value(utf8.encode(marker)),
          ),
        );
      final scripts = <String>[];
      final host = makeHost(client, scripts, ShellCredentialCustody('token'));
      await host.handleMessage(
        frame(<String, Object>{
          't': 'open',
          'id': 's-mime-${contentType ?? 'missing'}',
          'channel': 'chat-generation-events',
          'params': '{"generationId":"generation-mime"}',
          'credit': 1,
        }),
      );
      await waitFor(() => scripts.isNotEmpty, reason: 'MIME failure');
      final reply = parseSingleArgumentFrame(scripts.single);
      expect(reply['t'], 'error');
      expect(reply['failure'], 'transport-error');
      expect(scripts.join(), isNot(contains(marker)));
      await host.close();
    }
  });

  test('navigation aborts observation and drops buffered response callbacks', () async {
    final responseBytes = StreamController<List<int>>();
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(statusCode: 200, contentType: 'text/event-stream', bytes: responseBytes.stream),
      );
    final scripts = <String>[];
    final host = makeHost(client, scripts, ShellCredentialCustody('token'));
    await host.handleMessage(
      frame(<String, Object>{
        't': 'open',
        'id': 's-navigation',
        'channel': 'chat-generation-events',
        'params': '{"generationId":"generation-navigation"}',
        'credit': 2,
      }),
    );
    await waitFor(() => client.requests.length == 1);
    await host.resetForNavigation();
    expect(client.requests.single.aborted, isTrue);
    responseBytes.add(utf8.encode('late'));
    await responseBytes.close();
    await Future<void>.delayed(Duration.zero);
    expect(scripts, isEmpty);
    expect(host.activeSessionCount, 0);
    await host.close();
  });
}
