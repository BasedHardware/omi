import 'dart:io';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

/// Aggregate of existing CaptureSeams types plus missing I/O boundaries.
/// All fields required; supplying some fakes can never select production defaults.
class CaptureDependencies {
  const CaptureDependencies({
    required this.wal,
    required this.phoneMic,
    required this.batchSupported,
    required this.auth,
    required this.connectivity,
    required this.now,
    required this.scheduling,
    required this.preferences,
    required this.ble,
    required this.openSocket,
    required this.owner,
    required this.location,
    required this.localSegments,
    required this.codec,
    required this.microphonePermission,
    required this.refreshConversation,
    required this.telemetry,
    required this.ensureDeviceConnection,
  });
  final Future<DeviceConnection?> Function(String) ensureDeviceConnection;
  final RecordingLifecycleTelemetry telemetry;
  final IWalService wal;
  final IMicRecorderService phoneMic;
  final bool batchSupported;
  final CaptureAuthBoundary auth;
  final CaptureConnectivityBoundary connectivity;
  final DateTime Function() now;
  final CaptureScheduling scheduling;
  final SharedPreferencesUtil preferences;
  final CaptureBleListeners ble;
  final CaptureSocketOpen openSocket;
  final CaptureSessionOwner owner;
  final ConversationLocationCapture location;
  final LocalSegmentStore localSegments;
  final Future<BleAudioCodec> Function(String) codec;
  final Future<bool> Function() microphonePermission;
  final Future<void> Function() refreshConversation;
}

/// Production must use this exact constructor path too. No test-only subclass.
/// Owner/device-lookup stay on [CaptureDependencies] for later cuts; this step
/// forwards every seam CaptureController already accepts.
CaptureProvider composeCaptureProvider(CaptureDependencies dependencies) => CaptureProvider(
      walService: dependencies.wal,
      phoneMicRecorder: dependencies.phoneMic,
      phoneMicBatchSupported: dependencies.batchSupported,
      authBoundary: dependencies.auth,
      connectivity: dependencies.connectivity,
      now: dependencies.now,
      scheduling: dependencies.scheduling,
      preferences: dependencies.preferences,
      bleListeners: dependencies.ble,
      openSocket: dependencies.openSocket,
      conversationLocationCapture: dependencies.location,
      inProgressConversationLoader: dependencies.refreshConversation,
      audioCodecLoader: dependencies.codec,
      microphonePermissionRequester: dependencies.microphonePermission,
      recordingTelemetry: dependencies.telemetry,
      localSegmentStore: dependencies.localSegments,
    );

/// Composition entry signature for main.dart. Builder must resolve defaults
/// ONLY here, after refusing FLUTTER_TEST; no static/eager default evaluation.
CaptureProvider composeProductionCaptureProvider({
  LocalSegmentStore? localSegmentStore,
  CaptureExternalActions? externalActions,
}) {
  if (Platform.environment.containsKey('FLUTTER_TEST') || const bool.fromEnvironment('FLUTTER_TEST')) {
    throw UnsupportedError('composeProductionCaptureProvider refuses FLUTTER_TEST');
  }
  throw UnimplementedError('C1 production composition root');
}
