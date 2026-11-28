import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import '../support/capture/scripted_device_connection.dart';
import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_async_boundaries_test.dart' show HeldLocation;
import 'c1_composition_test.dart' show InertMic, dependencies;
import 'c1_location_completion_test.dart' show PhoneSpy, WalSpy;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('stop invalidates location before waiting for WAL finalization', () async {
    final dir = await Directory.systemTemp.createTemp('t10-stop-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final pendant = BtDevice(id: 'c1-pendant', name: 'Omi', type: DeviceType.omi, rssi: -40);
      world.deviceConnection = ScriptedDeviceConnection();
      final location = HeldLocation();
      final d = dependencies(world: world, preferences: SharedPreferencesUtil(), location: location);
      final phone = PhoneSpy(world.wal.getSyncs().phone);
      final deps = CaptureDependencies(
          wal: WalSpy(phone),
          phoneMic: InertMic(),
          batchSupported: false,
          microphonePermission: () async => false,
          auth: d.auth,
          connectivity: d.connectivity,
          now: d.now,
          scheduling: d.scheduling,
          preferences: d.preferences,
          ble: d.ble,
          openSocket: d.openSocket,
          owner: d.owner,
          location: location,
          localSegments: d.localSegments,
          codec: d.codec,
          refreshConversation: d.refreshConversation,
          telemetry: d.telemetry,
          ensureDeviceConnection: d.ensureDeviceConnection);
      final p = composeCaptureProvider(deps);
      await p.streamDeviceRecording(device: pendant);
      await pumpEventQueue();
      expect(location.captures, 1);
      final before = d.owner.token;
      phone.finalizeGate = Completer<void>();
      final stopping = p.stopStreamDeviceRecording();
      await pumpEventQueue();
      final invalidated = !d.owner.isCurrent(before);
      location.fix.complete(Geolocation(latitude: 1, longitude: 2, time: world.clock.now()));
      await pumpEventQueue();
      final staleUploads = location.uploads;
      location.upload.complete();
      phone.finalizeGate!.complete();
      await stopping;
      p.dispose();
      expect(invalidated, isTrue);
      expect(staleUploads, 0);
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
