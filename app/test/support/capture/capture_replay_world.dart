import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart' show SyncLocalFilesResponse;
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/scenarios/native_event_vector.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/mic/native_mic_recorder_service.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_service.dart';

import 'virtual_capture_time.dart';

class FakePhoneMicHostApi extends PhoneMicHostApi {
  int startCalls = 0;
  int stopCalls = 0;
  PhoneMicCaptureMode? lastStartMode;
  int? lastStartSessionId;
  final List<int> startSessionIds = [];
  final List<String> startStacks = [];
  bool nativeRecording = false;
  Object Function()? nextStartError;

  @override
  Future<void> start(PhoneMicCaptureMode mode, int sessionId) async {
    startStacks.add(StackTrace.current.toString());
    startCalls++;
    lastStartMode = mode;
    lastStartSessionId = sessionId;
    startSessionIds.add(sessionId);
    nativeRecording = true;
    final error = nextStartError;
    nextStartError = null;
    if (error != null) throw error();
  }

  @override
  Future<void> stop() async {
    stopCalls++;
    nativeRecording = false;
  }

  @override
  Future<bool> isRecording() async => nativeRecording;
}

/// Fake transport under the REAL [TranscriptSegmentSocketService]. Connects
/// and closes only when the scenario says so; records every payload sent.
class ScriptedPureSocket implements IPureSocket {
  IPureSocketListener? _listener;
  PureSocketStatus _status = PureSocketStatus.notConnected;

  /// When true, the next [connect] fails (mirrors an unreachable network).
  bool nextConnectFails = false;

  /// When set, connect fails while this returns false — models the network
  /// being down for NEW connections (an established transport is dropped via
  /// [emitClose] instead).
  bool Function()? connectAllowed;

  int connectAttempts = 0;
  int closeCalls = 0;
  final List<List<int>> sentBinary = <List<int>>[];
  final List<String> sentText = <String>[];

  @override
  PureSocketStatus get status => _status;

  @override
  Future<bool> connect() async {
    connectAttempts++;
    if (nextConnectFails || (connectAllowed != null && !connectAllowed!())) {
      nextConnectFails = false;
      _status = PureSocketStatus.notConnected;
      return false;
    }
    _status = PureSocketStatus.connected;
    // A real transport resolves on the event loop, after the caller has
    // subscribed its listener; mirror that ordering instead of a microtask,
    // which would fire before the controller subscribes.
    Timer.run(() {
      if (_status == PureSocketStatus.connected) _listener?.onConnected();
    });
    return true;
  }

  @override
  Future disconnect() async {
    _status = PureSocketStatus.disconnected;
    return;
  }

  @override
  Future stop() async {
    closeCalls++;
    _status = PureSocketStatus.notConnected;
    return;
  }

  @override
  void send(dynamic message) {
    if (message is List<int>) {
      sentBinary.add(message);
    } else {
      sentText.add(message.toString());
    }
  }

  @override
  void setListener(IPureSocketListener listener) => _listener = listener;

  @override
  void onMessage(dynamic message) => _listener?.onMessage(message);

  @override
  void onConnected() => _listener?.onConnected();

  @override
  void onClosed() => _listener?.onClosed();

  @override
  void onError(Object err, StackTrace trace) => _listener?.onError(err, trace);

  /// Network drops the transport without the local side stopping it.
  void emitClose([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    _listener?.onClosed(closeCode);
  }

  void emitError(Object err) {
    _status = PureSocketStatus.disconnected;
    _listener?.onError(err, StackTrace.current);
  }

  /// Server pushes a transcript/message event through the real decode path.
  void emitServerMessage(String json) => _listener?.onMessage(json);
}

/// One recorded upload attempt against the upload boundary.
class UploadAttempt {
  final DateTime at;
  final List<String> fileNames;
  final int totalBytes;
  final String? conversationId;
  final bool claimLiveCapture;

  UploadAttempt({
    required this.at,
    required this.fileNames,
    required this.totalBytes,
    required this.conversationId,
    required this.claimLiveCapture,
  });
}

/// Scripted upload boundary: the production [SyncUploadGate] with a
/// scenario-owned uploader and deterministic clock. Script entries are
/// consumed in order; the default (empty script) succeeds synchronously like
/// the server 200 fast-path.
class ScriptedUploads {
  final VirtualClock clock;
  final List<UploadAttempt> attempts = [];
  final List<Object Function()> script = [];

  /// When true, every upload attempt fails like a refused request — used to
  /// keep WALs retryable across phases that would otherwise auto-upload.
  bool failAll = false;

  ScriptedUploads(this.clock);

  void enqueueOutcome(Object Function() outcome) => script.add(outcome);

  /// Default success: server processed synchronously (200 fast-path).
  static UploadFilesResult success() {
    return UploadFilesResult.done(
      SyncLocalFilesResponse(newConversationIds: ['conv_test'], updatedConversationIds: []),
    );
  }

  SyncUploadGate buildGate() {
    return SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
        attempts.add(
          UploadAttempt(
            at: clock.now(),
            fileNames: files.map((f) => f.path.split(Platform.pathSeparator).last).toList(),
            totalBytes: files.fold(0, (sum, f) => sum + f.lengthSync()),
            conversationId: conversationId,
            claimLiveCapture: claimLiveCapture,
          ),
        );
        if (failAll) {
          throw StateError('synthetic refused upload');
        }
        if (script.isNotEmpty) {
          return script.removeAt(0)() as UploadFilesResult;
        }
        return success();
      },
      fairUseStatusLoader: () async => null,
      clock: clock.now,
    );
  }
}

/// The deterministic capture-recovery replay world.
///
/// Composes REAL production objects — [CaptureController],
/// [NativeMicRecorderService], [TranscriptSegmentSocketService],
/// [WalService]/[LocalWalSyncImpl], [RecordingTransferCoordinator] — over
/// controlled external I/O: virtual clock, manual scheduler, scripted socket
/// and upload boundary, fake native host. Restart evidence destroys and
/// reconstructs the whole object graph from the same real temp directory.
class CaptureReplayWorld {
  static final DateTime defaultStart = DateTime.utc(2026, 3, 1, 12, 0, 0);

  final Directory tempDir;
  final VirtualClock clock;
  final ScriptedUploads uploads;

  late ManualScheduler scheduler;
  late FakePhoneMicHostApi hostApi;
  late NativeMicRecorderService mic;
  late WalService wal;
  late StreamController<bool> connectivityStream;
  late RecordingTransferCoordinator coordinator;
  ScriptedPureSocket? socket;
  int socketCreates = 0;
  bool nextConnectFailsOnce = false;

  bool connected = true;
  bool signedIn = true;
  int tokenRefreshCalls = 0;
  final List<String> timeline = [];

  /// Server-side sync-job outcomes by job id, consulted by the reconciler
  /// through the injected job-status fetcher.
  final Map<String, SyncJobFetch> jobStatuses = {};

  _ReplayCaptureController? _controller;

  CaptureReplayWorld({required this.tempDir, required this.clock, required this.uploads});

  bool _disposed = false;
  bool _controllerDisposed = false;

  /// Boots a fresh world against [tempDir]. The caller owns [tempDir] cleanup.
  static Future<CaptureReplayWorld> boot({
    required Directory tempDir,
    DateTime? startTime,
    Map<String, Object> initialPrefs = const {},
    bool initiallyConnected = true,
    bool supportsBatch = true,
  }) async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final start = startTime ?? defaultStart;
    final world = CaptureReplayWorld(
      tempDir: tempDir,
      clock: VirtualClock(start),
      uploads: ScriptedUploads(VirtualClock(start)),
    );
    world.connected = initiallyConnected;
    await world._bootGeneration(supportsBatch: supportsBatch, initialPrefs: initialPrefs, firstBoot: true);
    return world;
  }

  Future<void> _bootGeneration({
    bool supportsBatch = true,
    Map<String, Object> initialPrefs = const {},
    bool firstBoot = false,
  }) async {
    if (firstBoot) {
      SharedPreferences.setMockInitialValues(initialPrefs);
    }
    await SharedPreferencesUtil.init();

    if (firstBoot) {
      SttModeResolver.instance = SttModeResolver(flagReader: () => false);
      if (!_envInitialized) {
        Env.init(const _SyntheticEnvFields());
        _envInitialized = true;
      }
    }

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );

    scheduler = ManualScheduler(clock: clock);
    hostApi = FakePhoneMicHostApi();
    mic = NativeMicRecorderService(
      hostApi: hostApi,
      registerFlutterApi: false,
      now: clock.now,
      periodic: scheduler.periodic,
    );
    wal = WalService(
      phoneUploadGate: uploads.buildGate(),
      phoneNow: clock.now,
      phonePeriodic: scheduler.periodic,
      phoneJobStatusFetcher: (jobId) async => jobStatuses[jobId] ?? const SyncJobFetch(SyncJobFetchOutcome.notFound),
    );
    wal.start();
    await wal.syncs.phone.walReady;
    connectivityStream = StreamController<bool>.broadcast();
    _controller = _ReplayCaptureController(
      world: this,
      walService: wal,
      phoneMicRecorder: mic,
      phoneMicBatchSupported: supportsBatch,
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: connected,
        changes: connectivityStream.stream,
        isConnected: () => connected,
      ),
      authBoundary: CaptureAuthBoundary(
        isSignedIn: () => signedIn,
        refreshIdToken: () async {
          tokenRefreshCalls++;
          return null;
        },
      ),
      now: clock.now,
      scheduling: scheduler,
      inProgressConversationLoader: () async {},
      audioCodecLoader: (deviceId) async => BleAudioCodec.pcm16,
      microphonePermissionRequester: () async => true,
      conversationLocationCapture: ConversationLocationCapture(
        isLocationServiceEnabled: () async => false,
        checkPermission: () async => LocationPermission.denied,
        requestPermission: () async => LocationPermission.denied,
        now: clock.now,
      ),
    );
    coordinator = RecordingTransferCoordinator(
      reconcile: () async {
        await wal.syncs.phone.reconcileUploadedWals();
      },
      discover: () async {},
      refreshPending: () async {},
      drain: () async {
        final response = await wal.syncs.phone.syncAll();
        final failed = (response?.localUploadFailures ?? 0) + (response?.localUploadPermanentFailures ?? 0) > 0;
        final needsReconciliation = (await wal.syncs.phone.getAllWals()).any((w) => w.status == WalStatus.uploaded);
        return RecordingTransferDrainResult(
          attempted: response != null,
          failed: failed,
          needsReconciliation: needsReconciliation,
        );
      },
      autoUploadEnabled: () => true,
      connectivityChanges: connectivityStream.stream,
      initiallyConnected: connected,
      clock: clock.now,
      scheduleCooldown: (delay, callback) => scheduler.once(delay, callback),
    );
    _controllerDisposed = false;
  }

  CaptureController get controller => _controller!;

  // -- Native event injection (drives the REAL NativeMicRecorderService) -----

  /// Injects [frameCount] deterministic PCM frames (10ms each) belonging to
  /// [sessionId]. Returns the injected audio bytes for later identity checks.
  List<List<int>> injectAudioFrames(int frameCount, {required int sessionId, int firstFrameIndex = 0}) {
    final frames = <List<int>>[];
    for (var i = 0; i < frameCount; i++) {
      final bytes = NativeEventVector.synthesizePcmFrame(firstFrameIndex + i);
      frames.add(bytes);
      mic.onAudioFrame(bytes, sessionId);
    }
    return frames;
  }

  void emitNativeState(PhoneMicCaptureState state, {int? sessionId}) {
    mic.onStateChanged(state, sessionId ?? hostApi.lastStartSessionId ?? 0);
  }

  void emitNativeError(String code, String message, {int? sessionId}) {
    mic.onCaptureError(code, message, sessionId ?? hostApi.lastStartSessionId ?? 0);
  }

  void emitBatchProgress(double seconds, {int? sessionId}) {
    mic.onBatchProgress(seconds, sessionId ?? hostApi.lastStartSessionId ?? 0);
  }

  // -- Scenario controls ------------------------------------------------------

  Future<void> startLiveCapture() async {
    await controller.streamRecording();
    await settle();
  }

  Future<void> stopLiveCapture({String reason = 'user_stopped'}) async {
    await controller.stopStreamRecording(reason: reason);
    await settle();
  }

  Future<void> startBatchCapture() async {
    await controller.startPhoneMicBatchForTesting();
    await settle();
  }

  void setConnected(bool value) {
    if (connected == value) return;
    connected = value;
    timeline.add('connectivity=${value ? 'restored' : 'lost'}');
    connectivityStream.add(value);
  }

  /// Let real async work (file I/O on temp files, microtask chains) settle
  /// after synchronous timer fires and injections.
  Future<void> settle({int rounds = 12}) async {
    for (var i = 0; i < rounds; i++) {
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(const Duration(milliseconds: 2));
    }
    await pumpEventQueue();
  }

  /// Advance virtual time by [duration], firing due timers in order, then
  /// settle real async work.
  Future<void> elapse(Duration duration) async {
    scheduler.elapse(duration);
    await settle();
  }

  // -- Process death and reconstruction ---------------------------------------

  /// Simulates process death: the object graph is dropped WITHOUT production
  /// cleanup (no dispose, no WAL stop, no finalize) — exactly what a kill
  /// leaves behind on disk.
  void killProcess() {
    timeline.add('process_killed');
    _controller = null;
    socket = null;
    connectivityStream.close();
  }

  /// Rebuilds the entire production graph from the same temp directory: a new
  /// [WalService] reloads wals.json + audio files from disk, a new controller
  /// and recorder start from that persisted state.
  Future<void> reconstructProcess({bool supportsBatch = true}) async {
    timeline.add('process_reconstructed');
    await _bootGeneration(supportsBatch: supportsBatch);
    await settle();
  }

  /// Dispose only the controller — used by cleanup-evidence tests that assert
  /// intermediate timer state between the controller's and the WAL's death.
  void disposeController() {
    _controllerDisposed = true;
    _controller?.dispose();
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    if (!_controllerDisposed) _controller?.dispose();
    coordinator.dispose();
    await connectivityStream.close();
    await wal.stop();
    SttModeResolver.debugResetInstance();
    SyncRateLimiter.instance.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
  }

  // -- Observations -----------------------------------------------------------

  Future<Map<WalStatus, int>> walCounts() async {
    final counts = <WalStatus, int>{};
    for (final w in await wal.syncs.phone.getAllWals()) {
      counts[w.status] = (counts[w.status] ?? 0) + 1;
    }
    return counts;
  }
}

/// Controller subclass whose only override is the sanctioned test seam
/// [CaptureController.openConversationSocket]: it returns a REAL
/// [TranscriptSegmentSocketService] over the scripted transport, mirroring
/// the pool (start, then null when not connected).
class _ReplayCaptureController extends CaptureController {
  final CaptureReplayWorld world;

  _ReplayCaptureController({
    required this.world,
    required super.walService,
    required super.phoneMicRecorder,
    required super.phoneMicBatchSupported,
    required super.connectivity,
    required super.authBoundary,
    required super.now,
    required super.scheduling,
    super.inProgressConversationLoader,
    super.audioCodecLoader,
    super.microphonePermissionRequester,
    super.conversationLocationCapture,
  });

  @override
  Future<TranscriptSegmentSocketService?> openConversationSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
  }) async {
    final transport = ScriptedPureSocket();
    transport.connectAllowed = () => world.connected;
    if (world.nextConnectFailsOnce) {
      transport.nextConnectFails = true;
      world.nextConnectFailsOnce = false;
    }
    world.socket = transport;
    world.socketCreates++;
    final service = TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      transport,
      source: source,
      clientConversationId: clientConversationId,
    );
    await service.start();
    if (service.state != SocketServiceState.connected) {
      return null;
    }

    return service;
  }
}

bool _envInitialized = false;

/// Minimal [EnvFields] for the replay world: no keys, synthetic local base
/// URL. Production code paths that log or read config on failure stay alive
/// without touching real credentials.
class _SyntheticEnvFields implements EnvFields {
  const _SyntheticEnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:0/';

  @override
  String? get posthogApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  bool? get useWebAuth => null;

  @override
  bool? get useAuthCustomToken => null;
}
