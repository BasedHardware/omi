import 'dart:async';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:disk_space_2/disk_space_2.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_upload_hold.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';
import 'package:omi/services/wals/mobile_standard_batch.dart';
import 'package:omi/services/live_preview/live_preview_composition.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_words_coordinator.dart';
import 'package:omi/services/live_preview/live_words_log.dart';
import 'package:omi/services/live_preview/vendor_live_words.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/calendar_capture_telemetry.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/capture/capture_continuity_monitor.dart';
import 'package:omi/env/env.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_session_owner.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/recording_lifecycle_telemetry.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/telemetry/client_telemetry_flags.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/app_foreground_time.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/experiments/capture_end_marker.dart';
import 'package:omi/services/experiments/mobile_batch_file_cap_gate.dart';
import 'package:omi/services/experiments/mobile_batch_upload_hold_gate.dart';
import 'package:omi/services/capture/capture_end.dart';
import 'package:omi/backend/http/api/capture_end.dart';

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
    this.openConversationSocket,
    required this.owner,
    required this.location,
    required this.localSegments,
    required this.codec,
    required this.microphonePermission,
    required this.refreshConversation,
    required this.telemetry,
    required this.ensureDeviceConnection,
    this.pendantReconnect,
    this.pendantReconnectBlocked,
    this.excludeSpeaker,
  });
  final Future<DeviceConnection?> Function(String) ensureDeviceConnection;
  final Future<void> Function(String deviceId)? pendantReconnect;
  final bool Function(String deviceId)? pendantReconnectBlocked;
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
  final CaptureConversationSocketOpen? openConversationSocket;
  final CaptureSessionOwner owner;
  final ConversationLocationCapture location;
  final LocalSegmentStore localSegments;
  final Future<BleAudioCodec> Function(String) codec;
  final Future<bool> Function() microphonePermission;
  final Future<void> Function() refreshConversation;
  final Future<bool> Function(String conversationId, List<String> segmentIds)? excludeSpeaker;
}

/// Production must use this exact constructor path too. No test-only subclass.
/// Owner/device-lookup stay on [CaptureDependencies] for later cuts; this step
/// forwards every seam CaptureController already accepts. The app tree
/// constructs capture only through [composeProductionCaptureProvider].
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
      openSocket: dependencies.openConversationSocket ??
          ({
            required codec,
            required sampleRate,
            required language,
            required force,
            source,
            clientConversationId,
            customSttConfig,
            geolocation,
          }) =>
              dependencies.openSocket(
                codec: codec,
                sampleRate: sampleRate,
                language: language,
                force: force,
                source: source,
                clientConversationId: clientConversationId,
                customSttConfig: customSttConfig,
              ),
      sessionOwner: dependencies.owner,
      conversationLocationCapture: dependencies.location,
      inProgressConversationLoader: dependencies.refreshConversation,
      audioCodecLoader: dependencies.codec,
      microphonePermissionRequester: dependencies.microphonePermission,
      recordingTelemetry: dependencies.telemetry,
      localSegmentStore: dependencies.localSegments,
      deviceConnectionLoader: dependencies.ensureDeviceConnection,
      pendantReconnect: dependencies.pendantReconnect,
      pendantReconnectBlocked: dependencies.pendantReconnectBlocked,
      excludeSpeaker: dependencies.excludeSpeaker,
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
  final provider = CaptureProvider(
    calendarGapMonitor: CalendarCaptureGapMonitor(
      localMeetings: GoogleCalendarService.knownMeetings,
      ownerKey: () =>
          SharedPreferencesUtil().getBool('google_calendar_connected') && SharedPreferencesUtil().uid.isNotEmpty
              ? GoogleCalendarService.meetingCacheOwner
              : '',
      load: (start, end) async => switch (await fetchCalendarCaptureWindows(start, end)) {
        ApiSuccess(:final data) => data,
        ApiFailure() => null, // Unavailable evidence is never an empty-success claim.
      },
      emit: (fields) => AnalyticsManager().track('Calendar Capture Gap Detected', properties: fields),
    ),
    sessionOwner: CaptureSessionOwner(
      coordinator: RecordingTransferCoordinator.instance,
      startForeground: () async {
        if (!Platform.isAndroid) {
          return;
        }
        await ForegroundUtil.initializeForegroundService();
        await ForegroundUtil.startForegroundTask();
      },
      stopForeground: ForegroundUtil.stopForegroundTask,
    ),
    localSegmentStore: localSegmentStore ?? LocalSegmentStore.appSupport(),
    externalActions: externalActions,
    // An Omi phone call pauses a streaming pendant and gives it back when it ends.
    omiCallState: PhoneCallProvider.callStateListenable,
  );
  unawaited(_installMobileStandardBatch(provider));
  final livePreview = composeLivePreview();
  if (livePreview != null) provider.installLivePreview(livePreview);
  final liveWords = livePreview == null ? null : _composeLiveWords(provider, livePreview);
  // Time with the app in front, and how much of it with capture active (App Foreground Ended).
  final foregroundTime = AppForegroundTime(capturing: () => _captureActive(provider));
  // omi-perf-allow: unselected-provider-listener -- the callback reads one bool and returns when capture is unchanged or the app is not in front
  provider.addListener(foregroundTime.onCaptureChanged);
  provider.lifetime.own(() => provider.removeListener(foregroundTime.onCaptureChanged));
  final lifecycle = AppLifecycleListener(onStateChange: (state) {
    provider.onAppLifecycleChanged(state);
    liveWords?.onLifecycle(state);
    foregroundTime.onLifecycle(state);
  });
  provider.lifetime.own(lifecycle.dispose);
  final initialLifecycle = WidgetsBinding.instance.lifecycleState;
  foregroundTime.start(initialLifecycle);
  if (initialLifecycle != null && initialLifecycle != AppLifecycleState.resumed) {
    provider.onAppLifecycleChanged(initialLifecycle);
  }
  if (Platform.isIOS) {
    // Presentation failure must never stop capture.
    unawaited(CaptureSystemSurface(provider, LiveActivityBridge()).start());
  }
  return provider;
}

/// A pendant is streaming or the phone is recording, and capture is not paused.
bool _captureActive(CaptureProvider provider) {
  if (provider.isPaused) return false;
  return switch (provider.recordingState) {
    RecordingState.deviceRecord ||
    RecordingState.record ||
    RecordingState.interrupted ||
    RecordingState.systemAudioRecord =>
      true,
    _ => false,
  };
}

/// Reliability experiment `vendor_recognizer_on_opened_app`: the vendor stream on the capture audio
/// taps and the coordinator that decides when it and the phone's recogniser run. Off, the taps only
/// reach an early return and nothing connects.
LiveWordsCoordinator _composeLiveWords(CaptureProvider provider, LivePreviewController livePreview) {
  final vendor = VendorLiveWords(
    onLines: livePreview.onVendorLines,
    onAudioSent: livePreview.noteAudioSent,
    log: (event, fields) => LiveWordsLog.event('vendor_$event', fields),
  );
  void onPendant(List<int> packet) => vendor.onPendantPacket(packet, provider.pendantTapCodec);
  provider.addDeviceAudioListener(onPendant);
  provider.addPhoneMicAudioListener(vendor.onPhonePcm);
  final coordinator = LiveWordsCoordinator(capture: provider, preview: livePreview, vendor: vendor)..start();
  // Reliability experiment live_words_cascade: an End cuts the live words and takes them for its request.
  provider.liveWordsOnEnd = coordinator.onEnd;
  provider.lifetime.own(() {
    provider.liveWordsOnEnd = null;
    provider.removeDeviceAudioListener(onPendant);
    provider.removePhoneMicAudioListener(vendor.onPhonePcm);
    coordinator.dispose();
  });
  return coordinator;
}

CaptureWedgeMonitor composeCaptureWedgeMonitor() {
  late final CaptureWedgeMonitor monitor;
  monitor = CaptureWedgeMonitor(
    featureGate: () => AnalyticsManager().isFeatureEnabled(captureRecoveryFeatureFlag),
    track: (event, properties) {
      final moved = event == 'Capture Ingress Health' || event == 'Capture Wedge Detected';
      if (moved && ClientTelemetryFlags.posthogRetirementEnabled) return;
      PlatformManager.instance.analytics.track(event, properties: properties);
    },
    bleRetry: (deviceId) async {
      final deviceService = ServiceManager.instance().device;
      await deviceService.recoverConnection(deviceId, shouldRetry: () => monitor.hasActiveEpisode(deviceId));
    },
    transferRetry: () => RecordingTransferCoordinator.instance.wake(WakeTrigger.dataStalled),
    appBuild: () => AnalyticsManager.appBuild,
    platform: () => AnalyticsManager.mobilePlatform,
  );
  return monitor;
}

/// Wires [CaptureContinuityMonitor] to the same analytics sink as the wedge
/// monitor. Its banner shows only in debug and TestFlight builds.
CaptureContinuityMonitor composeCaptureContinuityMonitor() {
  return CaptureContinuityMonitor(
    now: DateTime.now,
    track: (event, properties) {
      if (ClientTelemetryFlags.posthogRetirementEnabled) return;
      PlatformManager.instance.analytics.track(event, properties: properties);
    },
    dogfood: () => kDebugMode || Env.isTestFlight,
    appBuild: () => AnalyticsManager.appBuild,
    platform: () => AnalyticsManager.mobilePlatform,
  );
}

Future<void> _installMobileStandardBatch(CaptureProvider provider) async {
  try {
    final directory = await getApplicationDocumentsDirectory();
    final phone = ServiceManager.instance().wal.getSyncs().phone;
    await phone.walReady;
    if (provider.lifetime.isClosed) return;
    final coordinator = RecordingTransferCoordinator.instance;
    final hold = MobileBatchUploadHold(
      enabled: MobileBatchUploadHoldGate.enabled,
      foreground: coordinator.foregroundState.value,
      wake: () => unawaited(coordinator.wake(WakeTrigger.mobileBatchReady)),
      refreshFlags: MobileBatchUploadHoldGate.refresh,
    );
    final buffer = MobileBatchBuffer(
        directory: directory,
        onSealed: hold.sealed,
        onPublishFailed: hold.forget,
        publish: (wal) async {
          if (wal.ownerUid != SharedPreferencesUtil().uid) throw StateError('Batch owner retired');
          await phone.addExternalWal(wal, admittedGeneration: phone.sessionGeneration);
          if (wal.ownerUid != SharedPreferencesUtil().uid ||
              !await phone.hasDurableWal(wal, admittedGeneration: phone.sessionGeneration)) {
            throw StateError('Batch WAL index was not committed');
          }
          if (!hold.published(wal)) unawaited(coordinator.wake(WakeTrigger.periodic));
        });
    // Never delays the lane: capture starts on the default cap and the gate's
    // answer applies from the next frame after it arrives.
    unawaited(MobileBatchFileCapGate.maxFileSeconds().then((seconds) => buffer.maxFileSeconds = seconds));
    final lane = MobileStandardBatch(
      buffer: buffer,
      loadVad: SileroMobileBatchVad.load,
      freeDiskBytes: () async {
        final mb = await DiskSpace.getFreeDiskSpaceForPath(directory.path);
        return mb == null ? null : (mb * 1024 * 1024).round();
      },
      visibility: ListenClientState.instance,
      ownerUid: () => SharedPreferencesUtil().uid,
      now: DateTime.now,
    );
    final reporter = CaptureEndReporter(
      post: (signal, {required pendingWals, required sentAt}) async => switch (await postSyncCaptureEnd(
        recordingSessionId: signal.recordingSessionId,
        endType: signal.type.wire,
        lastSpeechAt: signal.lastSpeechAt,
        endDecidedAt: signal.decidedAt,
        sentAt: sentAt,
        pendingWals: pendingWals,
      )) {
        ApiSuccess(:final data) => data,
        // Kept by the reporter and retried on the next accepted file.
        ApiFailure() => false,
      },
      // Observation only: the reporter never seals, flushes or publishes.
      // Audio up to the end that is still being written or published counts
      // as pending until the capture lifecycle seals it and it is accepted.
      // Later chunks of trailing silence are not part of the ended recording.
      pendingWals: (signal) async {
        if (phone is! LocalWalSyncImpl) throw StateError('Capture-end WAL inventory unavailable');
        final unregistered = await lane.buffer.pendingJournalCount(signal.recordingSessionId,
            ownerUid: SharedPreferencesUtil().uid,
            through: signal.decidedAt,
            acceptedFileBytes: phone.captureEndAcceptedFileBytes(signal.recordingSessionId));
        final registered = phone.pendingWalsForRecording(signal.recordingSessionId, through: signal.decidedAt);
        return unregistered + registered;
      },
      disabled: () async => SharedPreferencesUtil().uid.isEmpty || await CaptureEndMarkerPolicy.disabled(),
      scope: () => (SharedPreferencesUtil().uid, phone.sessionGeneration),
      observationVersion: () => MobileBatchBuffer.journalRevision,
    );
    provider.captureEndReporter = reporter;
    provider.onMobileBatchCaptureEnded = (recordingSessionId) {
      if (hold.enabled()) buffer.seal();
      hold.captureEnded(recordingSessionId);
    };
    provider.lifetime
        .listenTo(coordinator.foregroundState, () => hold.setForeground(coordinator.foregroundState.value));
    final preview = provider.livePreview;
    if (preview != null) {
      void updatePreview() => hold.setPreview(preview.phase == LivePreviewPhase.streaming);
      provider.lifetime.listenTo(preview, updatePreview);
      updatePreview();
    }
    if (phone is LocalWalSyncImpl) {
      phone.mobileBatchUploadHold = hold;
      phone.onRecordingUploadAccepted = reporter.uploadAccepted;
    }
    provider.lifetime.own(() {
      hold.clear();
      if (phone is LocalWalSyncImpl && identical(phone.mobileBatchUploadHold, hold)) {
        phone.mobileBatchUploadHold = null;
        phone.onRecordingUploadAccepted = null;
      }
    });
    provider.installMobileStandardBatch(lane);
  } catch (_) {
    // Directory/plugin availability cannot interrupt the existing live path.
  }
}
