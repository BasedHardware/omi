import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/utils/enums.dart';

import '../support/capture/capture_replay_world.dart';
import '../support/spine/contract.dart';
import 'c1_composition_test.dart' show dependencies;

class HeldLocation extends ConversationLocationCapture {
  final fix = Completer<Geolocation?>();
  final upload = Completer<void>();
  int captures = 0;
  int uploads = 0;
  @override
  Future<Geolocation?> capture({bool promptIfDenied = true}) {
    captures++;
    return fix.future;
  }

  @override
  Future<void> uploadCompatibilitySnapshot(Geolocation value) {
    uploads++;
    return upload.future;
  }

  @override
  Future<Geolocation?> captureAndUpload({bool promptIfDenied = true}) async {
    final value = await capture(promptIfDenied: promptIfDenied);
    if (value != null) await uploadCompatibilitySnapshot(value);
    return value;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  contractTest('C1 location fix from obsolete session must not start compatibility upload', () async {
    final dir = await Directory.systemTemp.createTemp('c1-location-');
    final w = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      w.disposeController();
      final location = HeldLocation();
      final d = dependencies(world: w, preferences: SharedPreferencesUtil(), location: location);
      final p = composeCaptureProvider(d);
      await p.streamRecording();
      await pumpEventQueue();
      expect(location.captures, 1);
      d.owner.replaceSession('different-account');
      location.fix.complete(Geolocation(latitude: 1, longitude: 2, time: w.clock.now()));
      location.upload.complete();
      await pumpEventQueue();
      expect(location.uploads, 0);
      p.dispose();
    } finally {
      await w.dispose();
      await dir.delete(recursive: true);
    }
  });

  contractTest('C1 pending auth refresh cannot reconnect after capture generation changes', () async {
    final dir = await Directory.systemTemp.createTemp('c1-auth-');
    final w = await CaptureReplayWorld.boot(tempDir: dir);
    try {
      w.disposeController();
      final refresh = Completer<Object?>();
      var refreshes = 0;
      var opens = 0;
      final d = dependencies(
          world: w,
          preferences: SharedPreferencesUtil(),
          auth: CaptureAuthBoundary(
              isSignedIn: () => true,
              refreshIdToken: () {
                refreshes++;
                return refresh.future;
              }),
          open: (
              {required codec,
              required sampleRate,
              required language,
              required force,
              source,
              clientConversationId,
              customSttConfig}) async {
            opens++;
            return null;
          });
      final p = composeCaptureProvider(d);
      p.updateRecordingState(RecordingState.systemAudioRecord);
      p.onClosed(4001);
      await pumpEventQueue();
      expect(refreshes, 1);
      d.owner.replaceSession('different-account');
      refresh.complete(null);
      w.scheduler.elapse(const Duration(seconds: 30));
      await pumpEventQueue();
      expect(opens, 0);
      p.dispose();
    } finally {
      await w.dispose();
      await dir.delete(recursive: true);
    }
  });
}
