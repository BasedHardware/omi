import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/listen_socket_host.dart';

void main() {
  test('native Listen evidence audio is the exact deterministic PCM16 sequence', () {
    final audio = deterministicListenEvidenceAudio();
    expect(audio.length, 3200);
    for (final sample in <int>[0, 1, 1599]) {
      final value = audio[sample * 2] | (audio[sample * 2 + 1] << 8);
      final signed = value >= 0x8000 ? value - 0x10000 : value;
      expect(signed, ((sample * 257) % 24001) - 12000);
    }
  });

  test('native Listen evidence waits for the protocol-ready service frame', () {
    expect(isListenProtocolReady('{"type":"service_status","status":"ready"}'), isTrue);
    expect(isListenProtocolReady('{"type":"service_status","status":"starting"}'), isFalse);
    expect(isListenProtocolReady('{"type":"open"}'), isFalse);
    expect(isListenProtocolReady('not-json'), isFalse);
  });

  test('native Listen evidence gate sends exact audio once to a hermetic local service', () async {
    // red-proof: send on socket open instead of accepting service_status ready,
    // or omit the one-shot gate; this test sees zero or duplicate binary sends.
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final accepted = Completer<List<int>>();
    server.transform(WebSocketTransformer()).listen((socket) {
      socket.add(jsonEncode(<String, String>{'type': 'service_status', 'status': 'ready'}));
      socket.listen((data) {
        if (data is List<int> && !accepted.isCompleted) accepted.complete(data);
      });
    });

    final client = await WebSocket.connect('ws://127.0.0.1:${server.port}/v4/listen');
    addTearDown(client.close);
    final gate = NativeListenEvidenceGate();
    var sends = 0;
    client.listen((data) {
      if (data is! String) return;
      final audio = gate.acceptServiceFrame(data);
      if (audio != null) {
        sends++;
        client.add(audio);
      }
      expect(gate.acceptServiceFrame(data), isNull, reason: 'a duplicate ready frame cannot send again');
    });
    final bytes = await accepted.future;
    expect(bytes, deterministicListenEvidenceAudio());
    expect(sends, 1);
  });

  test('iOS production socket composition targets the API authority with the shell bearer', () {
    final authority = ShellTransportAuthority(
      baseUrl: Uri.parse('https://staging.example.test/api'),
      token: 'shell-token',
      runId: 'run-listen-proof',
    );
    final http = authority.makeHttpHost();
    final result = authority.prepareListen('/v4/listen?language=en');
    expect(http.baseUrl, authority.baseUrl);
    expect(http.hasCredential, isTrue);
    expect(result.failure, isNull);
    expect(result.request?.url.toString(), 'wss://staging.example.test/v4/listen?language=en');
    expect(result.request?.url.toString(), isNot(contains('omi-ui://local')));
    expect(result.request?.headers['authorization'], 'Bearer shell-token');
    expect(result.request?.headers['x-omi-client-id'], 'run-listen-proof::ios');
    http.closeForTest();
  });

  test('authority validates raw run identity and suffixes ios exactly once', () {
    final valid = ShellTransportAuthority(
      baseUrl: Uri.parse('https://api.example'),
      token: 'shell-token',
      runId: 'run-evidence_01',
    );
    expect(valid.clientIdentity, 'run-evidence_01::ios');
    valid.makeHttpHost().closeForTest();

    for (final raw in <String>['', 'unsafe value', 'already::ios', 'anonymous', 'overflow', '__reserved']) {
      expect(
        () => ShellTransportAuthority(baseUrl: Uri.parse('https://api.example'), token: 'shell-token', runId: raw),
        throwsArgumentError,
        reason: raw,
      );
    }
  });

  test('an empty host can reset on every document navigation', () async {
    final host = ShellTransportAuthority(
      baseUrl: Uri.parse('https://api.example'),
      token: 'shell-token',
      runId: 'run-navigation',
    ).makeListenHost();
    await host.resetForNavigation();
    await host.resetForNavigation();
    await host.close();
  });
}
