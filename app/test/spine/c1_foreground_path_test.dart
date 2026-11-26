import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import '../support/capture/scripted_device_connection.dart';
import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_composition_test.dart' show dependencies;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 device capture leaves foreground service ownership with the injected owner', () async {
    pendingContract('C1');
    final dir = await Directory.systemTemp.createTemp('c1-foreground-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    final startGate = Completer<void>();
    try {
      world.disposeController();
      final pendant = BtDevice(id: 'c1-pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
      world.deviceConnection = ScriptedDeviceConnection();
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
      await p.streamDeviceRecording(device: pendant);
      expect(owner.foregroundRunning, isFalse);
      expect(effects, isEmpty, reason: 'device stream does not start a phone microphone service');

      final start = owner.setForegroundRequired(true);
      await pumpEventQueue();
      expect(effects, ['start']);
      final stop = owner.setForegroundRequired(false);
      startGate.complete();
      await start;
      await stop;
      expect(effects, ['start', 'stop']);

      await p.stopStreamDeviceRecording();
      p.dispose();
      await pumpEventQueue();
      expect(effects, ['start', 'stop']);
    } finally {
      if (!startGate.isCompleted) startGate.complete();
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
