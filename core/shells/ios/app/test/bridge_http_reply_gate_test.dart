import 'package:flutter_test/flutter_test.dart';

import '../lib/bridge_http_host.dart';

void main() {
  test('sender-bound document ids reject an outgoing post after provisional navigation', () {
    final gate = BridgeHttpReplyGate(maxEntries: 2);

    gate.beginDocument(null);
    expect(gate.accept('unowned', 'h1'), isFalse, reason: 'a URL without a shell coordinate accepts no request');

    const documentA = 'document-a';
    gate.beginDocument(documentA);
    expect(gate.accept(documentA, 'h1'), isTrue);
    expect(gate.accept(documentA, 'h1'), isFalse, reason: 'a document receives at most one reply per id');

    const documentB = 'document-b';
    gate.beginDocument(documentB);
    expect(
      gate.accept(documentA, 'h2'),
      isFalse,
      reason: 'an outgoing document post received after B starts is rejected before dispatch',
    );
    expect(gate.accept(documentB, 'h1'), isTrue, reason: 'a new document restarts its JS-local request sequence');
    expect(gate.accept(documentA, 'h1'), isFalse, reason: 'a settled late reply cannot target the new document');
    expect(gate.accept(documentB, 'h1'), isFalse, reason: 'the current document still rejects duplicates');
    expect(gate.owns(documentA), isFalse, reason: 'a prior in-flight reply is fenced after navigation');
    expect(gate.owns(documentB), isTrue);

    expect(gate.accept(documentB, 'h2'), isTrue);
    expect(gate.accept(documentB, 'h3'), isTrue);
    expect(gate.accept(documentB, 'h1'), isTrue, reason: 'settled-id retention remains deterministically bounded');
  });

  test('owned navigation overwrites caller coordinates and mints a fresh value', () {
    final host = BridgeHttpHost(
      baseUrl: Uri.parse('http://127.0.0.1:4851'),
      custody: ShellCredentialCustody('fixture-token'),
      clientIdentity: 'fixture-client',
    );
    addTearDown(host.closeForTest);

    final first = host.ownDocument(
      Uri.parse('omi-ui://local/index.html?route=memories&__omiHttpDocument=caller-value'),
    );
    final second = host.ownDocument(Uri.parse('omi-ui://local/index.html?route=tasks'));

    expect(first.queryParameters['__omiHttpDocument'], 'd1');
    expect(second.queryParameters['__omiHttpDocument'], 'd2');
    expect(first.queryParameters['route'], 'memories');
    expect(second.queryParameters['route'], 'tasks');
  });
}
