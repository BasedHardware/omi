import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/live_finalize_gate.dart';

void main() {
  test('a second double-tap within 3 s is ignored, a later one ends the conversation again', () {
    var now = DateTime.utc(2026, 10, 23, 4);
    final gate = LiveFinalizeGate(clock: () => now);
    expect(gate.allowsDoubleTap, isTrue);
    gate.markFinalized();
    now = now.add(const Duration(seconds: 2));
    expect(gate.allowsDoubleTap, isFalse);
    now = now.add(const Duration(seconds: 1));
    expect(gate.allowsDoubleTap, isTrue);
  });
}
