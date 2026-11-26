import 'dart:async';
import 'package:omi/services/capture/calendar_capture_gap_monitor.dart';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart' show SyncLocalFilesResponse;
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/wal_service.dart';

import 'scripted_device_connection.dart';

import 'virtual_capture_time.dart';

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

  /// Every send and local close in order: the text itself, `<binary>` or `<close>`.
  final List<String> wire = <String>[];

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
    wire.add('<close>');
    _status = PureSocketStatus.notConnected;
    return;
  }

  @override
  void send(dynamic message) {
    if (message is List<int>) {
      sentBinary.add(message);
      wire.add('<binary>');
    } else {
      sentText.add(message.toString());
      wire.add(message.toString());
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
  final String? captureEvidence;

  UploadAttempt({
    required this.at,
    required this.fileNames,
    required this.totalBytes,
    required this.conversationId,
    required this.claimLiveCapture,
    required this.captureEvidence,
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

  /// Sees each upload's files while they still exist (a completed upload may
  /// delete them), e.g. to follow audio custody into the server.
  void Function(List<File> files)? onUploadFiles;

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
      uploader: (
        files, {
        onUploadProgress,
        conversationId,
        captureEvidence,
        recordingSessionId,
        audioStartSeconds,
        audioEndSeconds,
        claimLiveCapture = false,
        geolocation,
      }) async {
        onUploadFiles?.call(files);
        attempts.add(
          UploadAttempt(
            at: clock.now(),
            fileNames: files.map((f) => f.path.split(Platform.pathSeparator).last).toList(),
            totalBytes: files.fold(0, (sum, f) => sum + f.lengthSync()),
            conversationId: conversationId,
            claimLiveCapture: claimLiveCapture,
            captureEvidence: captureEvidence,
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
  final BleAudioCodec pendantCodec;

  late ManualScheduler scheduler;
  late WalService wal;
  late StreamController<bool> connectivityStream;
  late StreamController<void> networkChangeStream;
  late RecordingTransferCoordinator coordinator;
  ScriptedPureSocket? socket;
  int socketCreates = 0;
  bool autoUploadAllowed = true;

  /// The local_preview declaration of each socket the controller opened.
  final List<bool> localPreviewRequests = [];
  final List<String?> socketRecordingIds = [];

  /// Every transcription socket the controller opened, in order, with the source it declared.
  final List<({String? source, ScriptedPureSocket transport})> sockets = [];

  /// The pendant's BLE link, when a scenario connects one.
  ScriptedDeviceConnection? deviceConnection;

  /// The Omi phone-call state capture observes (PhoneCallProvider.callStateListenable in the app).
  final ValueNotifier<PhoneCallState> omiCall = ValueNotifier(PhoneCallState.idle);
  bool nextConnectFailsOnce = false;

  bool connected = true;
  bool signedIn = true;
  int processCalls = 0;

  /// Runs when the controller asks the server to process the in-progress conversation.
  void Function()? onProcessInProgress;

  /// When set, Process Now returns this outcome instead of a transport miss.
  Future<InProgressProcessOutcome> Function()? processOutcome;

  /// Optional real-index write barrier for close/admission race scenarios. Null preserves the
  /// production persistence path; callers that override it own writing the supplied inventory.
  Future<void> Function(List<Wal>)? phonePersistWals;

  /// Server deletes of discarded recordings, by recording id, in order.
  final List<String> discardDeletes = [];

  /// The answer to each discard delete; null answers deleted.
  bool Function(String id)? deleteDiscardedResult;
  int tokenRefreshCalls = 0;
  final List<String> timeline = [];

  /// Server-side sync-job outcomes by job id, consulted by the reconciler
  /// through the injected job-status fetcher.
  final Map<String, SyncJobFetch> jobStatuses = {};
  final List<({String jobId, DateTime at})> jobPolls = [];

  final List<Map<String, Object?>> coverageEvents = [];

  _ReplayCaptureController? _controller;

  CaptureReplayWorld({required this.tempDir, required this.clock, required this.uploads, required this.pendantCodec});

  Future<BleAudioCodec> Function(String)? audioCodecLoader;
  CalendarCaptureGapMonitor? calendarGapMonitor;
  Future<void> Function(String, bool)? deviceMuteWriter;
  Future<bool?> Function(String)? deviceMuteReader;
  CaptureWedgeMonitor? captureWedgeMonitor;

  bool _disposed = false;
  bool _controllerDisposed = false;

  /// Boots a fresh world against [tempDir]. The caller owns [tempDir] cleanup.
  static Future<CaptureReplayWorld> boot({
    required Directory tempDir,
    DateTime? startTime,
    Map<String, Object> initialPrefs = const {},
    bool initiallyConnected = true,
    BleAudioCodec pendantCodec = BleAudioCodec.pcm16,
    CalendarCaptureGapMonitor? calendarGapMonitor,
    Future<void> Function(String, bool)? deviceMuteWriter,
    Future<bool?> Function(String)? deviceMuteReader,
    CaptureWedgeMonitor? captureWedgeMonitor,
    Future<void> Function(List<Wal>)? phonePersistWals,
  }) async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final start = startTime ?? defaultStart;
    final world = CaptureReplayWorld(
      tempDir: tempDir,
      clock: VirtualClock(start),
      uploads: ScriptedUploads(VirtualClock(start)),
      pendantCodec: pendantCodec,
    );
    world.calendarGapMonitor = calendarGapMonitor;
    world.deviceMuteWriter = deviceMuteWriter;
    world.deviceMuteReader = deviceMuteReader;
    world.captureWedgeMonitor = captureWedgeMonitor;
    world.phonePersistWals = phonePersistWals;
    world.connected = initiallyConnected;
    await world._bootGeneration(initialPrefs: initialPrefs, firstBoot: true);
    return world;
  }

  Future<void> _bootGeneration({
    Map<String, Object> initialPrefs = const {},
    bool firstBoot = false,
  }) async {
    if (firstBoot) {
      SharedPreferences.setMockInitialValues(initialPrefs);
    }
    await SharedPreferencesUtil.init();
    if (firstBoot) {
      SyncRateLimiter.instance.clear();
      SyncRateLimiter.instance.clockForTesting = clock.now;
      SyncJobPoller.instance.resetForTesting(clock: clock.now);
    }

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
    wal = WalService(
      phonePersistWals: phonePersistWals,
      phoneUploadGate: uploads.buildGate(),
      phoneNow: clock.now,
      phonePeriodic: scheduler.periodic,
      phoneJobStatusFetcher: (jobId) async {
        jobPolls.add((jobId: jobId, at: clock.now()));
        return jobStatuses[jobId] ?? const SyncJobFetch(SyncJobFetchOutcome.notFound);
      },
      phoneCoverageTelemetry: coverageEvents.add,
      // The replay world has no real disk-space plugin; report ample space so
      // the storage-admission gate proves capacity instead of failing closed.
      phoneFreeDiskBytes: () async => 1 << 40,
    );
    wal.start();
    await wal.syncs.phone.walReady;
    connectivityStream = StreamController<bool>.broadcast();
    networkChangeStream = StreamController<void>.broadcast();
    _controller = _ReplayCaptureController(
      world: this,
      calendarGapMonitor: calendarGapMonitor,
      captureWedgeMonitor: captureWedgeMonitor,
      walService: wal,
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: connected,
        changes: connectivityStream.stream,
        networkChanges: networkChangeStream.stream,
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
      deviceConnectionLoader: (deviceId) async => deviceConnection,
      deviceMuteWriter: deviceMuteWriter,
      deviceMuteReader: deviceMuteReader,
      omiCallState: omiCall,
      deleteDiscardedConversation: (id) async {
        discardDeletes.add(id);
        return deleteDiscardedResult?.call(id) ?? true;
      },
      discardDeleteRetryDelays: const [Duration.zero, Duration.zero, Duration.zero],
      processInProgressOutcome: () async {
        processCalls++;
        onProcessInProgress?.call();
        final custom = processOutcome;
        if (custom != null) return custom();
        return const InProgressProcessOutcome(absence: ProcessAbsence.transport);
      },
      audioCodecLoader: (deviceId) => audioCodecLoader?.call(deviceId) ?? Future.value(pendantCodec),
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
      autoUploadEnabled: () => autoUploadAllowed,
      connectivityChanges: connectivityStream.stream,
      networkChanges: networkChangeStream.stream,
      initiallyConnected: connected,
      clock: clock.now,
      scheduleCooldown: (delay, callback) => scheduler.once(delay, callback),
    );
    _controllerDisposed = false;
  }

  CaptureController get controller => _controller!;

  void setConnected(bool value) {
    if (connected == value) return;
    connected = value;
    timeline.add('connectivity=${value ? 'restored' : 'lost'}');
    connectivityStream.add(value);
  }

  /// The active interface changed (wifi -> cellular) without ever going offline.
  void emitNetworkChange() {
    timeline.add('network=changed');
    networkChangeStream.add(null);
  }

  /// Drain work started by timer callbacks and injections: WAL file writes
  /// returned as Futures from async periodic callbacks, coordinator recovery
  /// passes (including unawaited cooldown wakes), and event-queue microtasks.
  /// Coordinator-idle is not durable I/O. Quiescence is observed — no sleeps.
  Future<void> settle({int maxTurns = 64}) async {
    for (var i = 0; i < maxTurns; i++) {
      await scheduler.waitForCallbackIo();
      await coordinator.waitUntilIdle();
      await pumpEventQueue();
      await scheduler.waitForCallbackIo();
      await coordinator.waitUntilIdle();
      if (!coordinator.hasInFlight && !scheduler.hasInFlightIo) return;
    }
    throw StateError('CaptureReplayWorld.settle: coordinator/timer IO did not go idle after $maxTurns turns');
  }

  /// Advance virtual time by [duration], firing due timers in order, then
  /// settle real async work (including cooldown wakes started with unawaited).
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
    networkChangeStream.close();
  }

  /// Rebuilds the entire production graph from the same temp directory: a new
  /// [WalService] reloads wals.json + audio files from disk, a new controller
  /// and recorder start from that persisted state.
  Future<void> reconstructProcess() async {
    timeline.add('process_reconstructed');
    await _bootGeneration();
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
    // Finish timer-callback file writes and in-flight drain/index writes
    // before callers delete [tempDir]. Coordinator-idle is not enough.
    await scheduler.waitForCallbackIo();
    await coordinator.waitUntilIdle();
    if (!_controllerDisposed) _controller?.dispose();
    coordinator.dispose();
    await connectivityStream.close();
    await networkChangeStream.close();
    await wal.stop();
    SttModeResolver.debugResetInstance();
    SyncRateLimiter.instance.clear();
    SyncRateLimiter.instance.clockForTesting = null;
    SyncJobPoller.instance.resetForTesting();
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
    required super.connectivity,
    required super.authBoundary,
    required super.now,
    required super.scheduling,
    super.inProgressConversationLoader,
    super.audioCodecLoader,
    super.conversationLocationCapture,
    super.deviceConnectionLoader,
    super.processInProgressOutcome,
    super.deleteDiscardedConversation,
    super.discardDeleteRetryDelays,
    super.omiCallState,
    super.calendarGapMonitor,
    super.deviceMuteWriter,
    super.deviceMuteReader,
    super.captureWedgeMonitor,
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
    Geolocation? geolocation,
    bool localPreview = false,
  }) async {
    final transport = ScriptedPureSocket();
    world.localPreviewRequests.add(localPreview);
    world.socketRecordingIds.add(clientConversationId);
    transport.connectAllowed = () => world.connected;
    if (world.nextConnectFailsOnce) {
      transport.nextConnectFails = true;
      world.nextConnectFailsOnce = false;
    }
    world.socket = transport;
    world.socketCreates++;
    world.sockets.add((source: source, transport: transport));
    final service = TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      transport,
      source: source,
      clientConversationId: clientConversationId,
      customSttMode: customSttConfig?.isEnabled ?? false,
      localPreview: localPreview,
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
