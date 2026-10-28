import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/lag_recorder.dart';
import 'package:omi/utils/analytics/lag_work_registry.dart';

void main() {
  test('nested identical tags have independent tokens and completed spans survive delayed ticks', () {
    var now = 100;
    final registry = LagWorkRegistry(nowUs: () => now);
    final first = registry.begin(LagWork.upload);
    now = 200;
    final second = registry.begin(LagWork.upload);
    now = 300;
    registry.end(first);
    registry.end(first); // duplicate end cannot retire another token
    expect(registry.overlapping(350, 400), ['upload']);
    now = 500;
    registry.end(second);
    expect(registry.overlapping(100, 600), ['upload']);
    expect(registry.overlapping(501, 600), isEmpty);
  });

  test('bounded registry keeps active work and safely ignores evicted tokens', () {
    var now = 1;
    final registry = LagWorkRegistry(nowUs: () => now, capacity: 2);
    final first = registry.begin(LagWork.sync);
    final old = registry.begin(LagWork.walLoad);
    registry.end(old);
    now = 2;
    final replacement = registry.begin(LagWork.upload);
    registry.end(old);
    expect(registry.begin(LagWork.indexSave), 0);
    expect(registry.dropped, 1);
    expect(registry.overlapping(2, 3), ['sync', 'upload']);
    registry.end(first);
    registry.end(replacement);
  });

  test('stall and retained local report include work that ended before the watchdog callback', () {
    var now = 1000000;
    final registry = LagWorkRegistry(nowUs: () => now);
    final events = <Map<String, Object?>>[];
    final recorder = LagRecorder(emit: (_, fields) => events.add(fields), nowUs: () => now, workRegistry: registry);
    final token = registry.begin(LagWork.reconcilePoll);
    now += 400000;
    registry.end(token);
    now += 1;
    recorder.recordStall(400000);
    expect(events.single['work_in_flight'], ['reconcilePoll']);
    recorder.writeReport('test');
    final retained = (events.last['worst_stalls'] as List).single as Map;
    expect(retained['work_in_flight'], ['reconcilePoll']);
    now += 2000000;
    recorder.recordStall(100000);
    expect(events.last['work_in_flight'], isEmpty);
  });

  test('finally cleanup preserves attribution on errors without leaving active tokens', () async {
    var now = 100;
    final registry = LagWorkRegistry(nowUs: () => now);
    Future<void> work() async {
      final token = registry.begin(LagWork.walLoad);
      try {
        throw StateError('synthetic');
      } finally {
        now = 200;
        registry.end(token);
      }
    }

    await expectLater(work(), throwsStateError);
    expect(registry.overlapping(100, 200), ['walLoad']);
    expect(registry.overlapping(201, 300), isEmpty);
  });
}
