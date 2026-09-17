import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

typedef CaptureSocketOpen = Future<TranscriptSegmentSocketService?> Function({
  required BleAudioCodec codec,
  required int sampleRate,
  required String language,
  required bool force,
  String? source,
  String? clientConversationId,
  CustomSttConfig? customSttConfig,
});

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
    required this.analytics,
  });
  final Future<DeviceConnection?> Function(String) ensureDeviceConnection;
  final AnalyticsManager analytics;
  final RecordingLifecycleTelemetry telemetry;
  final IWalService wal;
  final IMicRecorderService phoneMic;
  final bool batchSupported;
  final CaptureAuthBoundary auth;
  final CaptureConnectivityBoundary connectivity;
  final DateTime Function() now;
  final CaptureScheduling scheduling;
  final SharedPreferencesUtil preferences;
  final BleBridge ble;
  final CaptureSocketOpen openSocket;
  final CaptureSessionOwner owner;
  final ConversationLocationCapture location;
  final LocalSegmentStore localSegments;
  final Future<BleAudioCodec> Function(String) codec;
  final Future<bool> Function() microphonePermission;
  final Future<void> Function() refreshConversation;
}

/// Production must use this exact constructor path too. No test-only subclass.
CaptureProvider composeCaptureProvider(CaptureDependencies dependencies) =>
    throw UnimplementedError('C1 forward every dependency to CaptureProvider and CaptureController');

/// Composition entry signature for main.dart. Builder must resolve defaults
/// ONLY here, after refusing FLUTTER_TEST; no static/eager default evaluation.
CaptureProvider composeProductionCaptureProvider() => throw UnimplementedError('C1 production composition root');
