import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

import '../../support/capture/virtual_capture_time.dart';

class _MutePrefs implements SharedPreferencesUtil {
  @override
  bool get deviceMuted => true;
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected preferences read: ${i.memberName}');
}

class _BatchPrefs extends _MutePrefs {
  bool muted = true;
  @override
  bool get batchMuted => muted;
}

class _InertWal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Construction must not start WAL: ${i.memberName}');
}

class _InertMic implements IMicRecorderService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Construction must not start mic: ${i.memberName}');
}

CaptureDependencies _deps({
  SharedPreferencesUtil? preferences,
  CaptureConnectivityBoundary? connectivity,
  CaptureScheduling? scheduling,
}) {
  final clock = VirtualClock(DateTime.utc(2026));
  return CaptureDependencies(
    ensureDeviceConnection: (_) async => null,
    wal: _InertWal(),
    phoneMic: _InertMic(),
    batchSupported: false,
    auth: CaptureAuthBoundary(isSignedIn: () => true, refreshIdToken: () async => null),
    connectivity: connectivity ??
        CaptureConnectivityBoundary(initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
    now: clock.now,
    scheduling: scheduling ?? ManualScheduler(clock: clock),
    preferences: preferences ?? _MutePrefs(),
    ble: _NoopBle(),
    openSocket: ({
      required codec,
      required sampleRate,
      required language,
      required force,
      source,
      clientConversationId,
      customSttConfig,
    }) async =>
        null,
    owner: CaptureSessionOwner(
      coordinator: RecordingTransferCoordinator(
        reconcile: () async {},
        discover: () async {},
        refreshPending: () async {},
        drain: () async => const RecordingTransferDrainResult.skipped(),
        autoUploadEnabled: () => false,
      ),
      startForeground: () async {},
      stopForeground: () async {},
    ),
    location: ConversationLocationCapture(
      isLocationServiceEnabled: () async => false,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async => LocationPermission.denied,
      upload: (_) async => false,
      now: clock.now,
    ),
    localSegments: LocalSegmentStore.disabled(),
    codec: (_) async => BleAudioCodec.pcm16,
    microphonePermission: () async => true,
    refreshConversation: () async {},
    telemetry: RecordingLifecycleTelemetry(emitter: (_, __) {}, idFactory: () => 'synthetic', clock: clock.now),
  );
}

class _NoopBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('composeCaptureProvider routes wal/mic/auth/clock/scheduling/connectivity/prefs/ble/socket', () {
    final source = File('lib/services/capture/capture_composition.dart').readAsStringSync();
    final start = source.indexOf('CaptureProvider composeCaptureProvider');
    final end = source.indexOf('CaptureProvider composeProductionCaptureProvider');
    final body = source.substring(start, end);
    expect(body, contains('walService: dependencies.wal'));
    expect(body, contains('phoneMicRecorder: dependencies.phoneMic'));
    expect(body, contains('authBoundary: dependencies.auth'));
    expect(body, contains('now: dependencies.now'));
    expect(body, contains('scheduling: dependencies.scheduling'));
    expect(body, contains('connectivity: dependencies.connectivity'));
    expect(body, contains('preferences: dependencies.preferences'));
    expect(body, contains('bleListeners: dependencies.ble'));
    expect(body, contains('openConversationSocket'));
    expect(body, contains('openConversationSocket ??'));
    expect(body, contains('dependencies.openSocket('));
    expect(body, contains('sessionOwner: dependencies.owner'));
    final providerSource = File('lib/providers/capture_provider.dart').readAsStringSync();
    expect(providerSource, contains('super.walService'));
    expect(providerSource, contains('super.phoneMicRecorder'));
    expect(providerSource, contains('super.phoneMicBatchSupported'));
    expect(providerSource, contains('super.authBoundary'));
    expect(providerSource, contains('super.now'));
    expect(providerSource, contains('super.scheduling'));
    expect(providerSource, contains('super.connectivity'));
    expect(providerSource, contains('super.preferences'));
    expect(providerSource, contains('super.bleListeners'));
    expect(providerSource, contains('super.openSocket'));
    expect(providerSource, contains('super.sessionOwner'));
  });

  test('composeCaptureProvider uses injected connectivity, not ConnectivityService', () {
    final connectivity = CaptureConnectivityBoundary(
      initiallyConnected: false,
      changes: const Stream.empty(),
      isConnected: () => false,
    );
    final provider = composeCaptureProvider(_deps(connectivity: connectivity));
    expect(provider.runtimeType, CaptureProvider);
    expect(provider.isConnected, isFalse);
    expect(provider.isPaused, isTrue);
    provider.dispose();
  });

  test('injected preferences remain authoritative after construction', () {
    final prefs = _BatchPrefs();
    final provider = composeCaptureProvider(_deps(preferences: prefs));
    expect(provider.offlineMuted, isTrue);
    prefs.muted = false;
    expect(provider.offlineMuted, isFalse);
    provider.dispose();
  });

  test('composeProductionCaptureProvider cannot construct production health-URL connectivity', () {
    expect(
      () => composeProductionCaptureProvider(),
      throwsA(isA<UnsupportedError>().having((e) => e.toString(), 'message', contains('FLUTTER_TEST'))),
    );
    final source = File('lib/services/capture/capture_composition.dart').readAsStringSync();
    final start = source.indexOf('CaptureProvider composeProductionCaptureProvider');
    final body = source.substring(start);
    expect(body, isNot(contains('ConnectivityService')));
    expect(body, isNot(contains('CaptureConnectivityBoundary.production')));
    expect(body, isNot(contains('https://api.omi.me/v1/health')));
    final refuse = body.indexOf("throw UnsupportedError('composeProductionCaptureProvider refuses FLUTTER_TEST')");
    expect(refuse, greaterThan(0));
    final after = body.substring(refuse);
    expect(after, contains('sessionOwner:'));
    expect(after, contains('CaptureSessionOwner('));
    expect(after, contains('RecordingTransferCoordinator.instance'));
    expect(after, contains('ForegroundUtil.initializeForegroundService'));
    expect(after, contains('ForegroundUtil.startForegroundTask'));
    expect(after, contains('ForegroundUtil.stopForegroundTask'));
    expect(after, contains('Platform.isAndroid'));
  });

  test('main.dart default capture construction is composeProductionCaptureProvider', () {
    final main = File('lib/main.dart').readAsStringSync();
    expect(RegExp(r'(?<![A-Za-z])CaptureProvider\s*\(').allMatches(main), isEmpty);
    expect(RegExp(r'composeProductionCaptureProvider\s*\(').allMatches(main).length, 2);
  });
}
