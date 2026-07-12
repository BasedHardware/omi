import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/mic/mic_arbiter.dart';
import 'package:omi/services/services.dart';

class FakeMic implements IMicRecorderService {
  int startCalls = 0;
  int stopCalls = 0;
  bool failNextStart = false;
  Function()? capturedOnStop;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    startCalls++;
    if (failNextStart) {
      failNextStart = false;
      throw Exception('recorder failed to start');
    }
    capturedOnStop = onStop;
  }

  @override
  void stop() {
    stopCalls++;
    capturedOnStop?.call();
    capturedOnStop = null;
  }
}

void main() {
  group('MicArbiter', () {
    test('same owner can re-acquire, different owner cannot', () {
      final arbiter = MicArbiter();
      expect(arbiter.tryAcquire('a'), isTrue);
      expect(arbiter.tryAcquire('a'), isTrue);
      expect(arbiter.tryAcquire('b'), isFalse);
      arbiter.release('a');
      expect(arbiter.tryAcquire('b'), isTrue);
    });

    test('release by non-owner is ignored', () {
      final arbiter = MicArbiter();
      arbiter.tryAcquire('a');
      arbiter.release('b');
      expect(arbiter.owner, 'a');
    });
  });

  group('ArbitratedMic', () {
    late MicArbiter arbiter;
    late FakeMic micA;
    late FakeMic micB;
    late ArbitratedMic a;
    late ArbitratedMic b;

    setUp(() {
      arbiter = MicArbiter();
      micA = FakeMic();
      micB = FakeMic();
      a = ArbitratedMic(inner: micA, arbiter: arbiter, owner: 'conversation');
      b = ArbitratedMic(inner: micB, arbiter: arbiter, owner: 'mic');
    });

    Future<void> startMic(ArbitratedMic mic) => mic.start(onByteReceived: (_) {});

    test('second stack contends while first holds the mic', () async {
      await startMic(a);
      expect(() => startMic(b), throwsStateError);
      expect(micB.startCalls, 0);
    });

    test('stop releases so the other stack can start', () async {
      await startMic(a);
      a.stop();
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('start failure releases the arbiter and rethrows', () async {
      micA.failNextStart = true;
      await expectLater(startMic(a), throwsException);
      await startMic(b);
      expect(micB.startCalls, 1);
    });

    test('natural stop (inner onStop) releases without an explicit stop()', () async {
      var stopped = false;
      await a.start(onByteReceived: (_) {}, onStop: () => stopped = true);
      // Simulate the recorder retiring itself (e.g. watchdog kill).
      micA.capturedOnStop!.call();
      expect(stopped, isTrue);
      await startMic(b);
      expect(micB.startCalls, 1);
    });
  });
}
