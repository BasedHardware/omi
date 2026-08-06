import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/live_audio_frame_pacer.dart';

void main() {
  test('paces a completed BLE batch at the codec frame interval', () {
    fakeAsync((async) {
      final sent = <List<int>>[];
      final pacer = LiveAudioFramePacer(
        framesPerSecond: 50,
        canSend: () => true,
        send: sent.add,
      );

      final delivery = pacer.enqueue([
        [1],
        [2],
        [3],
      ]);
      expect(delivery.accepted, isTrue);
      var completed = false;
      delivery.completed.then((sent) => completed = sent);
      expect(sent, isEmpty);

      async.elapse(const Duration(milliseconds: 19));
      expect(sent, isEmpty);
      async.elapse(const Duration(milliseconds: 1));
      expect(sent, [
        [1],
      ]);
      async.elapse(const Duration(milliseconds: 40));
      expect(sent, [
        [1],
        [2],
        [3],
      ]);
      async.flushMicrotasks();
      expect(completed, isTrue);
    });
  });

  test('disconnect rejects the queued batch so its durable WAL stays retryable', () {
    fakeAsync((async) {
      var connected = true;
      final sent = <List<int>>[];
      final pacer = LiveAudioFramePacer(
        framesPerSecond: 50,
        canSend: () => connected,
        send: sent.add,
      );

      final delivery = pacer.enqueue(List.generate(20, (index) => [index]));
      bool? delivered;
      delivery.completed.then((sent) => delivered = sent);
      async.elapse(const Duration(milliseconds: 40));
      expect(sent, [
        [0],
        [1],
      ]);

      connected = false;
      async.elapse(const Duration(milliseconds: 20));
      async.flushMicrotasks();
      expect(pacer.bufferedFrames, 0);
      expect(pacer.isActive, isFalse);
      expect(delivered, isFalse);
      expect(
          pacer.enqueue([
            [99]
          ]).accepted,
          isFalse);
    });
  });

  test('rejects a whole overflow batch instead of truncating audio', () {
    fakeAsync((async) {
      final sent = <List<int>>[];
      final pacer = LiveAudioFramePacer(
        framesPerSecond: 2,
        maxBufferedSeconds: 2,
        canSend: () => true,
        send: sent.add,
      );

      final delivery = pacer.enqueue(List.generate(10, (index) => [index]));
      expect(delivery.accepted, isFalse);
      expect(pacer.bufferedFrames, 0);

      async.elapse(const Duration(seconds: 2));
      expect(sent, isEmpty);
    });
  });

  test('accepts a second batch without dropping the first batch boundary', () {
    fakeAsync((async) {
      final sent = <List<int>>[];
      final pacer = LiveAudioFramePacer(
        framesPerSecond: 2,
        maxBufferedSeconds: 3,
        canSend: () => true,
        send: sent.add,
      );

      final first = pacer.enqueue([
        [1],
        [2],
      ]);
      final second = pacer.enqueue([
        [3],
        [4],
      ]);
      bool? firstDelivered;
      bool? secondDelivered;
      first.completed.then((sent) => firstDelivered = sent);
      second.completed.then((sent) => secondDelivered = sent);
      expect(first.accepted, isTrue);
      expect(second.accepted, isTrue);

      async.elapse(const Duration(seconds: 2));
      async.flushMicrotasks();
      expect(sent, [
        [1],
        [2],
        [3],
        [4],
      ]);
      expect(firstDelivered, isTrue);
      expect(secondDelivered, isTrue);
    });
  });
}
