import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

// Fail closed if this question-only scenario touches capture, sync or account data.
class _Wal implements IWalService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected WAL effect: ${i.memberName}');
}

class _Mic implements IMicRecorderService {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected mic effect: ${i.memberName}');
}

class _Ble implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

class _Conversations extends ChangeNotifier implements ConversationProvider {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected conversation effect: ${i.memberName}');
}

class _People extends ChangeNotifier implements PeopleProvider {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected people effect: ${i.memberName}');
}

class _Usage extends ChangeNotifier implements UsageProvider {
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected usage effect: ${i.memberName}');
}

/// Real capture, production external-actions adapter and tutorial state. Only OS,
/// codec and HTTP I/O are supplied by the caller. No capture defaults are resolved.
class PendantTutorialHarness {
  PendantTutorialHarness(this.messages,
      {Future<BleAudioCodec> Function(String)? codec, Future<DeviceConnection?> Function(String)? connection}) {
    final coordinator = RecordingTransferCoordinator(
      reconcile: () async {},
      discover: () async {},
      refreshPending: () async {},
      drain: () async => const RecordingTransferDrainResult.skipped(),
      autoUploadEnabled: () => false,
    );
    capture = composeCaptureProvider(CaptureDependencies(
      wal: _Wal(),
      phoneMic: _Mic(),
      batchSupported: false,
      auth: CaptureAuthBoundary(isSignedIn: () => true, refreshIdToken: () async => null),
      connectivity:
          CaptureConnectivityBoundary(initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
      now: DateTime.now,
      scheduling: const WallClockCaptureScheduling(),
      preferences: SharedPreferencesUtil(),
      ble: _Ble(),
      openSocket: (
              {required codec,
              required sampleRate,
              required language,
              required force,
              source,
              clientConversationId,
              customSttConfig}) async =>
          null,
      owner: CaptureSessionOwner(coordinator: coordinator, startForeground: () async {}, stopForeground: () async {}),
      location: ConversationLocationCapture(
          isLocationServiceEnabled: () async => false,
          checkPermission: () async => LocationPermission.denied,
          requestPermission: () async => LocationPermission.denied,
          upload: (_) async => false,
          now: DateTime.now),
      localSegments: LocalSegmentStore.disabled(),
      codec: codec ?? (_) async => BleAudioCodec.opus,
      microphonePermission: () async => false,
      refreshConversation: () async {},
      telemetry:
          RecordingLifecycleTelemetry(emitter: (_, __) {}, idFactory: () => 'tutorial-fixture', clock: DateTime.now),
      ensureDeviceConnection: connection ?? (_) async => null,
    ));
    capture.updateExternalActions(ProviderCaptureExternalActions(
      conversationProvider: _Conversations(),
      messageProvider: messages,
      peopleProvider: _People(),
      usageProvider: _Usage(),
    ));
    capture.deviceOnboardingProvider = tutorial;
    capture.updateRecordingDevice(
        BtDevice(name: 'Fixture pendant', id: 'fixture-pendant', type: DeviceType.omi, rssi: -40));
    tutorial
      ..startOnboarding()
      ..advanceStep();
  }
  final MessageProvider messages;
  final tutorial = DeviceOnboardingProvider();
  late final CaptureProvider capture;
  void press() => capture.handleButtonEventForTesting('fixture-pendant', 1);
  void feed() => capture.addVoiceCommandBytesForTesting(<int>[1, 2, 3]);
  void submit() {
    press();
    feed();
    press();
  }

  bool _disposed = false;
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    capture.dispose();
    tutorial.dispose();
    messages.dispose();
  }
}
