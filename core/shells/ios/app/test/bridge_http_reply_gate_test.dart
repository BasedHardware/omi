import 'package:flutter_test/flutter_test.dart';

import '../lib/bridge_http_host.dart';

void main() {
  test('reply ids are unique within a document and reusable after navigation', () {
    final gate = BridgeHttpReplyGate(maxEntries: 2);

    final documentA = gate.beginDocument();
    expect(gate.accept(documentA, 'h1'), isTrue);
    expect(gate.accept(documentA, 'h1'), isFalse, reason: 'a document receives at most one reply per id');

    final documentB = gate.beginDocument();
    expect(gate.accept(documentB, 'h1'), isTrue, reason: 'a new document restarts its JS-local request sequence');
    expect(gate.accept(documentA, 'h2'), isFalse, reason: 'an unsettled reply from the prior document is still stale');
    expect(gate.accept(documentA, 'h1'), isFalse, reason: 'a settled late reply cannot target the new document');
    expect(gate.accept(documentB, 'h1'), isFalse, reason: 'the current document still rejects duplicates');

    expect(gate.accept(documentB, 'h2'), isTrue);
    expect(gate.accept(documentB, 'h3'), isTrue);
    expect(gate.accept(documentB, 'h1'), isTrue, reason: 'settled-id retention remains deterministically bounded');
  });
}
