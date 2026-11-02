import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/capture/live_held_audio_state.dart';

void main() {
  test('older receipts without reset_at default to zero', () {
    final event = SttCapLiveHeldEvent.fromJson({'session_id': 'old', 'held_seconds': 0, 'paused': true});
    expect(event.resetAt, 0);
  });
  test('server persistence receipts own the count and resume state', () {
    final state = LiveHeldAudioState();
    SttCapLiveHeldEvent receipt(int seconds, bool paused) => SttCapLiveHeldEvent.fromJson({
          'session_id': 'socket-1',
          'held_seconds': seconds,
          'reset_at': 1793491200,
          'paused': paused,
        });
    expect(state.apply(receipt(0, true)), isTrue);
    expect(state.paused, isTrue);
    expect(state.heldSeconds, 0);
    expect(state.resetAt, 1793491200);
    state.apply(receipt(61, true));
    expect(state.heldSeconds, 61);
    state.apply(receipt(61, false));
    expect(state.paused, isFalse);
    expect(state.heldSeconds, 61);
  });

  test('foreign sessions and invalid receipts cannot alter the active count', () {
    final state = LiveHeldAudioState();
    state.apply(SttCapLiveHeldEvent(sessionId: 'a', heldSeconds: 60, paused: true));
    expect(state.apply(SttCapLiveHeldEvent(sessionId: 'b', heldSeconds: 900, paused: true)), isFalse);
    expect(state.apply(SttCapLiveHeldEvent(sessionId: 'a', heldSeconds: -1, paused: false)), isFalse);
    expect(state.heldSeconds, 60);
    expect(state.paused, isTrue);
    state.reset();
    expect(state.sessionId, isNull);
    expect(state.resetAt, 0);
    expect(state.heldSeconds, 0);
    expect(state.paused, isFalse);
    expect(state.apply(SttCapLiveHeldEvent(sessionId: 'b', heldSeconds: 2, paused: true)), isTrue);
    expect(state.heldSeconds, 2);
  });
}
