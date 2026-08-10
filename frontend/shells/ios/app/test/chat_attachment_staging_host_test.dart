import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/bridge_http_host.dart';
import 'package:omi_webview_proto/chat_attachment_staging_host.dart';
import 'package:omi_webview_proto/chat_bridge_javascript_sink.dart';

import 'chat_native_test_fakes.dart';

const expiry = '2026-08-11T12:00:00.000Z';

String p7Response({int size = 3, Map<String, Object>? additions}) =>
    jsonEncode(<String, Object>{
      'attachment': <String, Object>{
        'id': 'attachment-opaque-01',
        'mimeType': 'application/pdf',
        'sizeBytes': size,
        'state': 'staged',
        'expiresAt': expiry,
        ...?additions,
      },
    });

ChatAttachmentStagingHost makeHost({
  required FakeChatNativeHttpClient client,
  required ChatAttachmentPicker picker,
  required List<String> scripts,
  required ShellCredentialCustody custody,
}) {
  return ChatAttachmentStagingHost(
    baseUrl: Uri.parse('https://service.example.test/base'),
    custody: custody,
    clientIdentity: 'run-upload::ios',
    sink: ChatBridgeJavaScriptSink((source) async => scripts.add(source)),
    picker: picker,
    httpClient: client,
    boundaryFactory: () => 'omi-chat-test-boundary',
  );
}

Future<Map<String, dynamic>> stageAndReply(
  ChatAttachmentStagingHost host,
  List<String> scripts,
) async {
  await host.handleMessage('{"t":"pick-and-stage","id":"a1"}');
  await waitFor(() => scripts.isNotEmpty, reason: 'staging reply');
  return parseStagingReply(scripts.single);
}

void main() {
  test(
    'picker cancellation returns cancelled without opening an upload',
    () async {
      final client = FakeChatNativeHttpClient();
      final picker = FakeChatAttachmentPicker(null);
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: picker,
        scripts: scripts,
        custody: ShellCredentialCustody('token'),
      );
      final reply = await stageAndReply(host, scripts);
      expect(reply, <String, Object>{
        'ok': false,
        'id': 'a1',
        'reason': 'cancelled',
      });
      expect(client.requests, isEmpty);
      await host.close();
    },
  );

  test(
    '50 MiB file streams as exactly one multipart file and exact no-name P7 response succeeds',
    () async {
      // red-proof: replace `picked.openRead()` with whole-file bytes or add a
      // second multipart field; this fake exposes only the streaming seam and
      // the one-field content assertion fails.
      const chunkSize = 64 * 1024;
      const chunkCount = 800;
      const fileSize = chunkSize * chunkCount;
      final chunk = List<int>.filled(chunkSize, 0x41, growable: false);
      final picked = FakePickedChatAttachment(
        sizeBytes: fileSize,
        stream: Stream<List<int>>.fromIterable(
          List<List<int>>.filled(chunkCount, chunk),
        ),
      );
      final response = FakeChatNativeHttpResponse(
        statusCode: 201,
        contentType: 'application/json; charset=utf-8',
        bytes: Stream<List<int>>.value(utf8.encode(p7Response(size: fileSize))),
      );
      final client = FakeChatNativeHttpClient()..responses.add(response);
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(picked),
        scripts: scripts,
        custody: ShellCredentialCustody('native-upload-secret'),
      );
      final reply = await stageAndReply(host, scripts);

      expect(reply['ok'], isTrue);
      expect(reply['attachment'], <String, Object>{
        'id': 'attachment-opaque-01',
        'mimeType': 'application/pdf',
        'sizeBytes': fileSize,
        'expiresAt': expiry,
        'state': 'staged',
      });
      expect(jsonEncode(reply), isNot(contains('displayName')));
      expect(picked.openReadCalls, 1);
      final request = client.requests.single;
      expect(request.method, 'POST');
      expect(request.url.path, '/v1/chat-attachments');
      expect(request.followsRedirects, isFalse);
      expect(request.headers['authorization'], 'Bearer native-upload-secret');
      expect(request.headers['x-omi-contract-version'], '1.0.0');
      expect(request.headers['x-omi-client-id'], 'run-upload::ios');
      expect(
        request.headers['content-type'],
        'multipart/form-data; boundary=omi-chat-test-boundary',
      );
      expect(request.declaredContentLength, request.bodyByteCount);
      expect(
        'name="file"'.allMatches('${request.prefixText}${request.suffixText}'),
        hasLength(1),
      );
      expect(request.prefixText, isNot(contains('displayName')));
      expect(request.prefixText, isNot(contains('.pdf')));
      expect(request.prefixText, isNot(contains('Content-Type:')));
      expect(scripts.join(), isNot(contains('native-upload-secret')));
      expect(scripts.join(), isNot(contains('service.example.test')));
      await host.close();
    },
  );

  test(
    'unsafe P7 descriptors redirects and non-201 responses never expose server metadata',
    () async {
      final valid = <String, Object>{
        'id': 'attachment-opaque-01',
        'mimeType': 'application/pdf',
        'sizeBytes': 3,
        'state': 'staged',
        'expiresAt': expiry,
      };
      final cases = <({int status, bool redirect, Object body, String marker})>[
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {...valid, 'id': '../unsafe'},
          },
          marker: '../unsafe',
        ),
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {...valid, 'displayName': 'secret.pdf'},
          },
          marker: 'secret.pdf',
        ),
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {...valid, 'path': '/private/file'},
          },
          marker: '/private/file',
        ),
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {...valid, 'token': 'server-secret'},
          },
          marker: 'server-secret',
        ),
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {...valid, 'sizeBytes': 4},
          },
          marker: 'attachment-opaque-01',
        ),
        (
          status: 201,
          redirect: false,
          body: {
            'attachment': {'id': 'attachment-opaque-01'},
          },
          marker: 'attachment-opaque-01',
        ),
        (
          status: 201,
          redirect: false,
          body: {'attachment': valid, 'extra': true},
          marker: 'attachment-opaque-01',
        ),
        (
          status: 201,
          redirect: true,
          body: {'attachment': valid},
          marker: 'attachment-opaque-01',
        ),
        (
          status: 200,
          redirect: false,
          body: {'attachment': valid},
          marker: 'attachment-opaque-01',
        ),
        (status: 201, redirect: false, body: 'not-json', marker: 'not-json'),
      ];

      for (final item in cases) {
        final picked = FakePickedChatAttachment(
          sizeBytes: 3,
          stream: Stream<List<int>>.value(<int>[1, 2, 3]),
        );
        final raw = item.body is String
            ? item.body as String
            : jsonEncode(item.body);
        final client = FakeChatNativeHttpClient()
          ..responses.add(
            FakeChatNativeHttpResponse(
              statusCode: item.status,
              contentType: 'application/json',
              isRedirect: item.redirect,
              bytes: Stream<List<int>>.value(utf8.encode(raw)),
            ),
          );
        final scripts = <String>[];
        final host = makeHost(
          client: client,
          picker: FakeChatAttachmentPicker(picked),
          scripts: scripts,
          custody: ShellCredentialCustody('token'),
        );
        final reply = await stageAndReply(host, scripts);
        expect(reply, <String, Object>{
          'ok': false,
          'id': 'a1',
          'reason': 'shell-error',
        });
        expect(scripts.join(), isNot(contains(item.marker)));
        await host.close();
      }
    },
  );

  test(
    'caller metadata and signed-out custody are refused before upload dispatch',
    () async {
      final picked = FakePickedChatAttachment(
        sizeBytes: 3,
        stream: Stream<List<int>>.value(<int>[1, 2, 3]),
      );
      final client = FakeChatNativeHttpClient();
      final scripts = <String>[];
      final custody = ShellCredentialCustody('token');
      custody.observeResponse(
        method: 'DELETE',
        path: '/v1/session/current',
        status: 204,
      );
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(picked),
        scripts: scripts,
        custody: custody,
      );
      await host.handleMessage(
        '{"t":"pick-and-stage","id":"a-extra","displayName":"caller.pdf","path":"/tmp/caller","token":"caller-token"}',
      );
      await host.handleMessage('{"t":"pick-and-stage","id":"a-signed-out"}');
      expect(client.requests, isEmpty);
      expect(scripts, hasLength(2));
      expect(parseStagingReply(scripts[0])['reason'], 'shell-error');
      expect(parseStagingReply(scripts[1])['reason'], 'unavailable');
      expect(scripts.join(), isNot(contains('caller.pdf')));
      expect(scripts.join(), isNot(contains('/tmp/caller')));
      expect(scripts.join(), isNot(contains('caller-token')));
      await host.close();
    },
  );

  test('sign-out near misses retain authority for a new upload', () async {
    final custody = ShellCredentialCustody('token');
    custody.observeResponse(
      method: 'DELETE',
      path: '/v1/session/other',
      status: 204,
    );
    final client = FakeChatNativeHttpClient()
      ..responses.add(
        FakeChatNativeHttpResponse(
          statusCode: 201,
          contentType: 'application/json',
          bytes: Stream<List<int>>.value(utf8.encode(p7Response())),
        ),
      );
    final scripts = <String>[];
    final host = makeHost(
      client: client,
      picker: FakeChatAttachmentPicker(
        FakePickedChatAttachment(
          sizeBytes: 3,
          stream: Stream<List<int>>.value(<int>[1, 2, 3]),
        ),
      ),
      scripts: scripts,
      custody: custody,
    );
    final reply = await stageAndReply(host, scripts);
    expect(reply['ok'], isTrue);
    expect(client.requests.single.headers['authorization'], 'Bearer token');
    await host.close();
  });

  test(
    'an already opened upload lease may finish after exact sign-out',
    () async {
      final custody = ShellCredentialCustody('token');
      final client = FakeChatNativeHttpClient()
        ..demandGatedRequests = true
        ..responses.add(
          FakeChatNativeHttpResponse(
            statusCode: 201,
            contentType: 'application/json',
            bytes: Stream<List<int>>.value(utf8.encode(p7Response(size: 2))),
          ),
        );
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(
          FakePickedChatAttachment(
            sizeBytes: 2,
            stream: Stream<List<int>>.fromIterable(<List<int>>[
              <int>[1],
              <int>[2],
            ]),
          ),
        ),
        scripts: scripts,
        custody: custody,
      );
      await host.handleMessage('{"t":"pick-and-stage","id":"a-leased"}');
      await waitFor(() => client.requests.singleOrNull?.streamedChunks == 1);
      custody.observeResponse(
        method: 'DELETE',
        path: '/v1/session/current',
        status: 204,
      );
      client.requests.single.releaseDemand();
      await waitFor(() => client.requests.single.streamedChunks == 2);
      client.requests.single.releaseDemand();
      await waitFor(() => scripts.isNotEmpty, reason: 'leased upload reply');
      expect(parseStagingReply(scripts.single)['ok'], isTrue);

      await host.handleMessage('{"t":"pick-and-stage","id":"a-after"}');
      await waitFor(() => scripts.length == 2);
      expect(parseStagingReply(scripts.last)['reason'], 'unavailable');
      expect(client.requests, hasLength(1));
      await host.close();
    },
  );

  test(
    'navigation cancels the request and file stream and drops every late callback',
    () async {
      final fileBytes = StreamController<List<int>>();
      final picked = FakePickedChatAttachment(
        sizeBytes: 3,
        stream: fileBytes.stream,
      );
      final client = FakeChatNativeHttpClient()
        ..responses.add(
          FakeChatNativeHttpResponse(
            statusCode: 201,
            contentType: 'application/json',
            bytes: Stream<List<int>>.value(utf8.encode(p7Response())),
          ),
        );
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(picked),
        scripts: scripts,
        custody: ShellCredentialCustody('token'),
      );
      await host.handleMessage('{"t":"pick-and-stage","id":"a-navigation"}');
      await waitFor(
        () => client.requests.length == 1,
        reason: 'upload request',
      );
      await host.resetForNavigation();
      expect(client.requests.single.aborted, isTrue);
      fileBytes.add(<int>[1, 2, 3]);
      await fileBytes.close();
      await Future<void>.delayed(Duration.zero);
      expect(scripts, isEmpty);
      await host.close();
    },
  );

  test(
    'multipart omits per-part MIME for PDF PNG and text byte signatures',
    () async {
      // red-proof: restore the application/octet-stream part header; every case
      // fails before the platform-compatible body can be accepted.
      final bodies = <List<int>>[
        utf8.encode('%PDF-1.7\n'),
        <int>[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
        utf8.encode('plain text\n'),
      ];
      for (final body in bodies) {
        final client = FakeChatNativeHttpClient()
          ..responses.add(
            FakeChatNativeHttpResponse(
              statusCode: 201,
              contentType: 'Application/JSON; Charset=UTF-8',
              bytes: Stream<List<int>>.value(
                utf8.encode(p7Response(size: body.length)),
              ),
            ),
          );
        final scripts = <String>[];
        final host = makeHost(
          client: client,
          picker: FakeChatAttachmentPicker(
            FakePickedChatAttachment(
              sizeBytes: body.length,
              stream: Stream<List<int>>.value(body),
            ),
          ),
          scripts: scripts,
          custody: ShellCredentialCustody('token'),
        );
        final reply = await stageAndReply(host, scripts);
        expect(reply['ok'], isTrue);
        final request = client.requests.single;
        expect(request.prefixText, contains('name="file"; filename="upload"'));
        expect(request.prefixText, isNot(contains('Content-Type:')));
        expect(request.declaredContentLength, request.bodyByteCount);
        await host.close();
      }
    },
  );

  test(
    'addStream demand gates file production and cancellation interrupts it',
    () async {
      // red-proof: replace awaited request.addStream with synchronous add;
      // produced races to 3 while transport demand is held at one.
      var produced = 0;
      Stream<List<int>> source() async* {
        for (var value = 1; value <= 3; value += 1) {
          produced += 1;
          yield <int>[value];
        }
      }

      final client = FakeChatNativeHttpClient()
        ..demandGatedRequests = true
        ..responses.add(
          FakeChatNativeHttpResponse(
            statusCode: 201,
            contentType: 'application/json',
            bytes: Stream<List<int>>.value(utf8.encode(p7Response())),
          ),
        );
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(
          FakePickedChatAttachment(sizeBytes: 3, stream: source()),
        ),
        scripts: scripts,
        custody: ShellCredentialCustody('token'),
      );
      await host.handleMessage('{"t":"pick-and-stage","id":"a-demand"}');
      await waitFor(
        () => client.requests.singleOrNull?.streamedChunks == 1,
        reason: 'first demanded file chunk',
      );
      expect(produced, 1);
      client.requests.single.releaseDemand();
      await waitFor(
        () => client.requests.single.streamedChunks == 2,
        reason: 'second demanded file chunk',
      );
      expect(produced, 2);
      await host.resetForNavigation();
      expect(client.requests.single.aborted, isTrue);
      client.requests.single.releaseDemand();
      await Future<void>.delayed(Duration.zero);
      expect(produced, 2);
      expect(scripts, isEmpty);
      await host.close();
    },
  );

  test(
    'file shrink and growth are rejected by the streamed byte counter',
    () async {
      for (final item in <({int declared, List<int> body})>[
        (declared: 3, body: <int>[1, 2]),
        (declared: 3, body: <int>[1, 2, 3, 4]),
      ]) {
        final client = FakeChatNativeHttpClient()
          ..responses.add(
            FakeChatNativeHttpResponse(
              statusCode: 201,
              contentType: 'application/json',
            ),
          );
        final scripts = <String>[];
        final host = makeHost(
          client: client,
          picker: FakeChatAttachmentPicker(
            FakePickedChatAttachment(
              sizeBytes: item.declared,
              stream: Stream<List<int>>.value(item.body),
            ),
          ),
          scripts: scripts,
          custody: ShellCredentialCustody('token'),
        );
        final reply = await stageAndReply(host, scripts);
        expect(reply['reason'], 'shell-error');
        expect(client.requests.single.aborted, isTrue);
        await host.close();
      }
    },
  );

  test('50 MiB plus one is refused before openUrl', () async {
    final picked = FakePickedChatAttachment(
      sizeBytes: maxChatAttachmentBytes + 1,
      stream: const Stream<List<int>>.empty(),
    );
    final client = FakeChatNativeHttpClient();
    final scripts = <String>[];
    final host = makeHost(
      client: client,
      picker: FakeChatAttachmentPicker(picked),
      scripts: scripts,
      custody: ShellCredentialCustody('token'),
    );
    final reply = await stageAndReply(host, scripts);
    expect(reply['reason'], 'shell-error');
    expect(client.requests, isEmpty);
    expect(picked.openReadCalls, 0);
    await host.close();
  });

  test('staging refuses a missing or wrong response media type', () async {
    for (final contentType in <String?>[null, 'text/plain']) {
      final marker = 'server-body-must-not-cross';
      final client = FakeChatNativeHttpClient()
        ..responses.add(
          FakeChatNativeHttpResponse(
            statusCode: 201,
            contentType: contentType,
            bytes: Stream<List<int>>.value(utf8.encode(marker)),
          ),
        );
      final scripts = <String>[];
      final host = makeHost(
        client: client,
        picker: FakeChatAttachmentPicker(
          FakePickedChatAttachment(
            sizeBytes: 3,
            stream: Stream<List<int>>.value(<int>[1, 2, 3]),
          ),
        ),
        scripts: scripts,
        custody: ShellCredentialCustody('token'),
      );
      final reply = await stageAndReply(host, scripts);
      expect(reply['reason'], 'shell-error');
      expect(scripts.join(), isNot(contains(marker)));
      await host.close();
    }
  });
}
