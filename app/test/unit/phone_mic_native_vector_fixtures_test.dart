import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/scenarios/native_event_vector.dart';

/// Pins the canonical phone-mic native-event vector fixtures that the C5
/// Swift/Kotlin replay harnesses (ios/test/phone_mic_lifecycle_replay_test.rb,
/// android JVM PhoneMicLifecycleReplayTest) consume. Same file bytes on every
/// platform: if the fixtures drift from this Dart contract, this test fails
/// before any native lane reports a false pass.
void main() {
  final fixturesDir = Directory('${Directory.current.path}/test/fixtures/phone_mic_native_events');

  test('fixture directory holds the canonical vector set', () {
    final ids = fixturesDir
        .listSync()
        .whereType<File>()
        .map((f) => f.uri.pathSegments.last.replaceFirst('.json', ''))
        .toList()
      ..sort();
    expect(ids, [
      'phone-mic-idle-stop',
      'phone-mic-interruption-resume',
      'phone-mic-rebuild',
      'phone-mic-session-adoption',
      'phone-mic-stale-event',
      'phone-mic-start-error-engine',
      'phone-mic-start-error-permission',
      'phone-mic-start-running',
    ]);
  });
  test('every fixture parses as phone-mic-native-events/v1 with matching frame bytes', () {
    final files = fixturesDir.listSync().whereType<File>().toList();
    expect(files, isNotEmpty);
    var totalFrames = 0;
    for (final file in files) {
      var frameIndex = 0;
      final vector = NativeEventVector.fromJson(
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
      );
      expect(vector.schemaVersion, nativeEventVectorSchemaVersion);
      expect(vector.id, file.uri.pathSegments.last.replaceFirst('.json', ''));
      expect(vector.events, isNotEmpty);
      expect(vector.revision, 1, reason: '${vector.id}: revisions are immutable; edit = new revision');
      expect(vector.events.first.kind, NativeCaptureEventKind.stateChanged);
      final states = vector.events.where((e) => e.kind == NativeCaptureEventKind.stateChanged).toList();
      final expectedTerminal = vector.id == 'phone-mic-start-running' ? 'running' : 'idle';
      expect(states.last.state, expectedTerminal, reason: '${vector.id}: terminal state must be $expectedTerminal');
      final allowedSessionIds = vector.id == 'phone-mic-session-adoption'
          ? {vector.startSessionId, vector.startSessionId + 16}
          : {vector.startSessionId};
      for (final event in vector.events) {
        expect(allowedSessionIds.contains(event.sessionId), isTrue,
            reason: '${vector.id}: unexpected session id ${event.sessionId}');
        if (event.kind == NativeCaptureEventKind.audioFrame) {
          expect(event.pcmFrame, NativeEventVector.synthesizePcmFrame(frameIndex),
              reason: '${vector.id} frame $frameIndex must be the deterministic LCG frame');
          frameIndex++;
          totalFrames++;
        }
      }
    }
    expect(totalFrames, greaterThan(0), reason: 'fixtures must exercise audio frames');
  });

  test('stale-event vector places a frame across the rebuild boundary', () {
    final vector = NativeEventVector.fromJson(
      jsonDecode(File('${fixturesDir.path}/phone-mic-stale-event.json').readAsStringSync()) as Map<String, dynamic>,
    );
    final rebuildAt = vector.events.indexWhere((e) => e.state == 'rebuilding');
    final afterRebuild = vector.events.skip(rebuildAt + 1).takeWhile((e) => e.state != 'running');
    // The frame between `rebuilding` and the recovery to `running` is the
    // stale-delivery stimulus: native adapters must drop it (old epoch).
    expect(afterRebuild.any((e) => e.kind == NativeCaptureEventKind.audioFrame), isTrue);
  });

  test('error vectors are start-failure schedules that terminate idle without frames', () {
    for (final name in ['phone-mic-start-error-permission', 'phone-mic-start-error-engine']) {
      final vector = NativeEventVector.fromJson(
        jsonDecode(File('${fixturesDir.path}/$name.json').readAsStringSync()) as Map<String, dynamic>,
      );
      expect(vector.events.map((e) => e.state).whereType<String>().toList(), ['starting', 'idle'],
          reason: '$name: failed start resolves idle');
      expect(vector.events.any((e) => e.kind == NativeCaptureEventKind.audioFrame), isFalse);
    }
  });
}
