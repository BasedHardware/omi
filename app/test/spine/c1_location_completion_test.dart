import 'dart:io';
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_async_boundaries_test.dart' show HeldLocation;
import 'c1_composition_test.dart' show dependencies;

class PhoneSpy {
  PhoneSpy(this.real);
  final dynamic real;
  Completer<void>? finalizeGate;
  final published = <Geolocation?>[];
  Future<void> onAudioCodecChanged(BleAudioCodec codec) async => await real.onAudioCodecChanged(codec);
  void setDeviceInfo(String? id, String? name) => real.setDeviceInfo(id, name);
  void setSessionGeolocation(Geolocation? value) {
    published.add(value);
    real.setSessionGeolocation(value);
  }

  Future<void> finalizeCurrentSession() async {
    await finalizeGate?.future;
    await real.finalizeCurrentSession();
  }

  Future<void> stampConversationId(int start, String id) async => await real.stampConversationId(start, id);
}

class SyncSpy {
  SyncSpy(this.phone);
  final PhoneSpy phone;
}

class WalSpy implements IWalService {
  WalSpy(this.phone);
  final PhoneSpy phone;
  @override
  dynamic getSyncs() => SyncSpy(phone);
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected WAL operation: ${i.memberName}');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 old upload completion cannot publish geolocation into new capture WAL', () async {
    final dir = await Directory.systemTemp.createTemp('c1-upload-');
    final w = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      w.disposeController();
      final location = HeldLocation();
      final d = dependencies(world: w, preferences: SharedPreferencesUtil(), location: location);
      final phone = PhoneSpy(w.wal.getSyncs().phone);
      final deps = CaptureDependencies(
          wal: WalSpy(phone),
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
          location: location,
          localSegments: d.localSegments,
          codec: d.codec,
          microphonePermission: d.microphonePermission,
          refreshConversation: d.refreshConversation,
          telemetry: d.telemetry,
          ensureDeviceConnection: d.ensureDeviceConnection);

      final p = composeCaptureProvider(deps);
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 1);
      location.fix.complete(Geolocation(latitude: 1, longitude: 2, time: w.clock.now()));
      await pumpEventQueue();
      expect(location.uploads, 1);
      d.owner.replaceSession('new-generation');
      location.upload.complete();
      await pumpEventQueue();
      expect(phone.published.whereType<Geolocation>(), isEmpty);
      // Current work still publishes; an implementation that drops every result fails.
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 2);
      expect(phone.published.whereType<Geolocation>().single.latitude, 1);
      p.dispose();
    } finally {
      await w.dispose();
      await dir.delete(recursive: true);
    }
  });
  contractTest('C1 capture finalization completion cannot wake recovery for a later session', () async {
    final dir = await Directory.systemTemp.createTemp('c1-finalize-');
    final w = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      w.disposeController();
      var drains = 0;
      final coordinator = RecordingTransferCoordinator(
          reconcile: () async {},
          discover: () async {},
          refreshPending: () async {},
          autoUploadEnabled: () => true,
          drain: () async {
            drains++;
            return const RecordingTransferDrainResult.skipped();
          });
      final owner =
          CaptureSessionOwner(coordinator: coordinator, startForeground: () async {}, stopForeground: () async {});
      final d = dependencies(
          world: w,
          preferences: SharedPreferencesUtil(),
          open: (
              {required codec,
              required sampleRate,
              required language,
              required force,
              source,
              clientConversationId,
              customSttConfig}) async {
            final socket = TranscriptSegmentSocketService.withSocket(sampleRate, codec, language, ScriptedPureSocket());
            await socket.start();
            return socket;
          });
      final phone = PhoneSpy(w.wal.getSyncs().phone);
      final deps = CaptureDependencies(
          wal: WalSpy(phone),
          phoneMic: d.phoneMic,
          batchSupported: d.batchSupported,
          auth: d.auth,
          connectivity: d.connectivity,
          now: d.now,
          scheduling: d.scheduling,
          preferences: d.preferences,
          ble: d.ble,
          openSocket: d.openSocket,
          owner: owner,
          location: d.location,
          localSegments: d.localSegments,
          codec: d.codec,
          microphonePermission: d.microphonePermission,
          refreshConversation: d.refreshConversation,
          telemetry: d.telemetry,
          ensureDeviceConnection: d.ensureDeviceConnection);

      final p = composeCaptureProvider(deps);
      await p.changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);
      phone.finalizeGate = Completer<void>();
      p.onMessageEventReceived(ConversationProcessingStartedEvent(
          memory: ServerConversation(
              id: 'synthetic', createdAt: w.clock.now(), structured: Structured('fixture', 'fixture'))));
      w.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(drains, 0);
      owner.replaceSession('new-session');
      phone.finalizeGate!.complete();
      await pumpEventQueue();
      await coordinator.waitUntilIdle();
      expect(drains, 0);
      await owner.requestRecovery(WakeTrigger.userRetry);
      expect(drains, 1);
      p.dispose();
      await owner.close();
    } finally {
      await w.dispose();
      await dir.delete(recursive: true);
    }
  });
}
