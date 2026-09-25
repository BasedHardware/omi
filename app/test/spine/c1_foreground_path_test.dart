import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_composition_test.dart' show dependencies;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 real capture start-stop race routes foreground intent through injected owner', () async {
    final dir = await Directory.systemTemp.createTemp('c1-foreground-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final startGate = Completer<void>();
    try {
      world.disposeController();
      final effects = <String>[];
      final owner = CaptureSessionOwner(
          coordinator: world.coordinator,
          startForeground: () async {
            effects.add('start');
            await startGate.future;
          },
          stopForeground: () async {
            effects.add('stop');
          });
      final p = composeCaptureProvider(dependencies(world: world, preferences: SharedPreferencesUtil(), owner: owner));
      final starting = p.streamRecording();
      await pumpEventQueue();
      expect(effects, ['start']);
      final stopping = p.stopStreamRecording();
      await pumpEventQueue();
      expect(effects, ['start']);
      startGate.complete();
      await starting;
      await stopping;
      expect(effects, ['start', 'stop']);
      expect(owner.foregroundRunning, isFalse);
      await p.streamRecording();
      expect(effects, ['start', 'stop', 'start']);
      p.dispose();
      await pumpEventQueue();
      expect(effects, ['start', 'stop', 'start', 'stop']);
    } finally {
      if (!startGate.isCompleted) startGate.complete();
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
