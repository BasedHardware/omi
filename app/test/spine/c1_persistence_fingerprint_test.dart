import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/utils/enums.dart';

import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_composition_test.dart' show dependencies;

import 'c1_persistence_test.dart' show HeldStore;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 cancelled queued fingerprint cannot suppress identical content in the next generation', () async {
    final dir = await Directory.systemTemp.createTemp('c1-store-');
    final world = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      world.disposeController();
      final d = dependencies(world: world, preferences: SharedPreferencesUtil());
      final store = HeldStore();
      final deps = CaptureDependencies(
          ensureDeviceConnection: d.ensureDeviceConnection,
          wal: d.wal,
          phoneMic: d.phoneMic,
          batchSupported: d.batchSupported,
          auth: d.auth,
          connectivity: d.connectivity,
          now: d.now,
          scheduling: d.scheduling,
          preferences: d.preferences,
          ble: d.ble,
          openSocket: d.openSocket,
          owner: d.owner,
          location: d.location,
          localSegments: store,
          codec: d.codec,
          microphonePermission: d.microphonePermission,
          refreshConversation: d.refreshConversation,
          telemetry: d.telemetry);
      final p = composeCaptureProvider(deps);
      d.telemetry.prepare(source: 'phone_live');
      void publish(String text) {
        p.segments = [
          TranscriptSegment(
              id: 's',
              text: text,
              speaker: 'SPEAKER_00',
              isUser: false,
              personId: null,
              start: 0,
              end: 1,
              translations: [])
        ];
        p.updateRecordingState(RecordingState.record);
      }

      publish('issued');
      await pumpEventQueue();
      expect(store.calls, ['issued']);
      publish('queued-old');
      d.owner.replaceSession('new-user/new-session');
      store.gate.complete();
      await p.pendingLiveSegmentWrite;
      expect(store.calls, ['issued']);
      expect(store.writes, ['synthetic:issued']);
      // The skipped old write did not persist this content. The new generation must.
      publish('queued-old');
      await p.pendingLiveSegmentWrite;
      expect(store.calls, ['issued', 'queued-old']);
      p.dispose();
    } finally {
      await world.dispose();
      await dir.delete(recursive: true);
    }
  });
}
