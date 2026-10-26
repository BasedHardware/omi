import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_reconciler.dart';
import 'package:omi/services/wals/sync_transfer_keep_alive.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Real provider/coordinator/reconciler/phone owner. Only the device, network
/// and persistence boundaries are synthetic. Notifications follow WalService.
class _Service implements IWalService, IWalSyncListener {
  late final _Syncs syncs;
  IWalServiceListener? subscriber;

  _Service(SyncUploadGate gate, Future<SyncJobFetch> Function(String) status) {
    syncs = _Syncs(LocalWalSyncImpl(this, uploadGate: gate, jobStatusFetcher: status, persistWals: (_) async {}));
  }

  @override
  dynamic getSyncs() => syncs;
  @override
  void subscribe(IWalServiceListener subscription, Object context) => subscriber = subscription;
  @override
  void unsubscribe(Object context) => subscriber = null;
  @override
  void start() {}
  @override
  Future<void> stop() async {}
  @override
  void onWalUpdated() => subscriber?.onWalUpdated();
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) =>
      subscriber?.onWalSynced(wal, conversation: conversation);
}

class _Syncs {
  _Syncs(this.phone);
  final LocalWalSyncImpl phone;
  final List<Wal> deviceWals = [];
  final List<Wal> discoverable = [];
  int discoveries = 0;
  int uploads = 0;
  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;
  bool get isFlashPageSyncing => false;
  Future<List<Wal>> getAllWals() async => [...await phone.getAllWals(), ...deviceWals];
  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {
    discoveries++;
    deviceWals
      ..clear()
      ..addAll(discoverable);
  }

  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) async {
    uploads++;
    return phone.syncAll(progress: progress);
  }

  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) =>
      syncAll(progress: progress);
  void cancelSync() => phone.cancelSync();
  void clearUserData() {
    phone.clearUserData();
    deviceWals.clear();
  }
}

Wal _uploaded(String job) => Wal(
      timerStart: DateTime.now().millisecondsSinceEpoch ~/ 1000 - 600,
      codec: BleAudioCodec.pcm16,
      seconds: 60,
      storage: WalStorage.disk,
      status: WalStatus.uploaded,
      device: 'phone',
    )..jobId = job;

class _Client extends Fake implements HttpClient {
  _Client(this.body, this.requests);
  final String body;
  final List<String> requests;
  @override
  int? maxConnectionsPerHost;
  @override
  Duration idleTimeout = Duration.zero;
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async {
    requests.add(url.path);
    return _Request(body);
  }

  @override
  void close({bool force = false}) {}
}

class _Request extends Fake implements HttpClientRequest {
  _Request(this.body);
  final String body;
  @override
  HttpHeaders get headers => _Headers();
  @override
  bool followRedirects = false;
  @override
  int maxRedirects = 5;
  @override
  bool persistentConnection = true;
  @override
  int contentLength = 0;
  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();
  @override
  Future<HttpClientResponse> close() async => _Response(body);
  @override
  Future<HttpClientResponse> get done => close();
  @override
  void abort([Object? error, StackTrace? stackTrace]) {}
}

class _Response extends Stream<List<int>> implements HttpClientResponse {
  _Response(this.body);
  final String body;
  @override
  StreamSubscription<List<int>> listen(void Function(List<int>)? onData,
          {Function? onError, void Function()? onDone, bool? cancelOnError}) =>
      Stream.value(utf8.encode(body)).listen(onData, onError: onError, onDone: onDone, cancelOnError: cancelOnError);
  @override
  HttpHeaders get headers => _Headers();
  @override
  int get statusCode => HttpStatus.ok;
  @override
  String get reasonPhrase => 'OK';
  @override
  bool get isRedirect => false;
  @override
  List<RedirectInfo> get redirects => const [];
  @override
  bool get persistentConnection => true;
  @override
  int get contentLength => utf8.encode(body).length;
  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError('${invocation.memberName}');
}

class _Headers extends Fake implements HttpHeaders {
  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {}
  @override
  void forEach(void Function(String, List<String>) action) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final coordinator = RecordingTransferCoordinator.instance;
  late SyncUploadGate gate;
  SyncProvider? provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'autoSyncOfflineRecordings': false});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    SyncRateLimiter.instance.clear();
    Env.overrideApiBaseUrl('http://127.0.0.1:18950/');
    gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async =>
          throw StateError('auto-upload is disabled'),
    );
  });

  tearDown(() async {
    await coordinator.waitUntilIdle();
    provider?.dispose();
    provider = null;
    coordinator.dispose();
    SyncReconciler.instance.dispose();
    SyncRateLimiter.instance.clear();
    Env.clearApiBaseUrlOverride();
  });

  Future<void> start(_Service service, {SyncTransferKeepAlive? keepAlive}) async {
    provider = SyncProvider(
      walService: service,
      uploadGate: gate,
      waitForWalReady: (_) async {},
      keepAlive: keepAlive,
    );
    await provider!.initialized;
  }

  test('startup surfaces a completed server job without requiring another upload', () async {
    final wal = _uploaded('persisted-job');
    final conversation = ServerConversation(
      id: 'completed-conversation',
      createdAt: DateTime.utc(2026, 10, 21),
      structured: Structured('Saved conversation', 'Recovered after relaunch'),
      status: ConversationStatus.completed,
    );
    final service = _Service(
        gate,
        (_) async => SyncJobFetch(
              SyncJobFetchOutcome.ok,
              SyncJobStatusResponse.fromJson({
                'job_id': wal.jobId,
                'status': 'completed',
                'total_segments': 1,
                'processed_segments': 1,
                'successful_segments': 1,
                'failed_segments': 0,
                'result': {
                  'new_memories': [conversation.id],
                  'updated_memories': []
                },
              }),
            ));
    service.syncs.phone.testWals = [wal];
    final requests = <String>[];
    await HttpOverrides.runZoned(() async {
      await start(service);
      await coordinator.waitUntilIdle();
    }, createHttpClient: (_) => _Client(jsonEncode(conversation.toJson()), requests));

    expect(wal.status, WalStatus.synced);
    expect(requests, ['/v1/conversations/${conversation.id}']);
    expect(provider!.syncedConversationsPointers.map((p) => p.conversation.id), [conversation.id]);
    expect(service.syncs.uploads, 0);
    expect(provider!.uploadedWals, isEmpty);
  });

  test('startup discovers and publishes device backlog even with auto-upload disabled', () async {
    final service = _Service(gate, (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    final deviceWal = Wal(
      timerStart: 1000,
      codec: BleAudioCodec.pcm16,
      seconds: 120,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
    );
    service.syncs.discoverable.add(deviceWal);
    await start(service);
    await coordinator.waitUntilIdle();

    expect(service.syncs.discoveries, 1);
    expect(provider!.pendingWals, [deviceWal]);
    expect(service.syncs.uploads, 0, reason: 'discovery must preserve the auto-sync preference');
  });

  test('startup keeps a genuinely queued server recording pending without uploading it again', () async {
    final wal = _uploaded('still-queued');
    final service = _Service(
        gate,
        (id) async => SyncJobFetch(
              SyncJobFetchOutcome.ok,
              SyncJobStatusResponse.fromJson({'job_id': id, 'status': 'queued'}),
            ));
    service.syncs.phone.testWals = [wal];
    await start(service);
    await coordinator.waitUntilIdle();

    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, 'still-queued');
    expect(provider!.uploadedWals, [wal]);
    expect(provider!.syncedConversationsPointers, isEmpty);
    expect(service.syncs.uploads, 0);
  });

  test('a retired pass cannot reconcile the replacement account after native lease acquisition', () async {
    final lease = Completer<void>();
    var starts = 0;
    final keepAlive = SyncTransferKeepAlive(
      isAndroid: () => true,
      start: () {
        starts++;
        return lease.future;
      },
      stop: () async {},
    );
    final polled = <String>[];
    final service = _Service(gate, (id) async {
      polled.add(id);
      return SyncJobFetch(
          SyncJobFetchOutcome.ok,
          SyncJobStatusResponse.fromJson({
            'job_id': id,
            'status': 'completed',
            'result': {'new_memories': [], 'updated_memories': []},
          }));
    });
    await start(service, keepAlive: keepAlive);
    expect(starts, 1);
    provider!.clearUserData();
    final replacement = _uploaded('replacement-account-job');
    service.syncs.phone.testWals = [replacement];
    lease.complete();
    await coordinator.waitUntilIdle();

    expect(polled, isEmpty, reason: 'an old admitted pass must not adopt the replacement account');
    expect(service.syncs.discoveries, 0);
    expect(provider!.allWals, isEmpty);

    await coordinator.wake(WakeTrigger.foregrounded);
    await coordinator.waitUntilIdle();
    expect(polled, ['replacement-account-job'], reason: 'a newly admitted pass still recovers the current account');
    expect(replacement.status, WalStatus.synced);
  });

  test('a reconciliation result stays with the callback admitted before reattachment', () async {
    final started = Completer<void>();
    final status = Completer<SyncJobFetch>();
    final original = _Service(gate, (_) {
      started.complete();
      return status.future;
    });
    original.syncs.phone.testWals = [_uploaded('original-job')];
    final replacement = _Service(gate, (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    final surfaced = <String>[];
    final reconciler = SyncReconciler.instance;
    reconciler.attach(original.syncs.phone, (_) async => surfaced.add('original'));
    final pass = reconciler.poke();
    await started.future;
    reconciler.attach(replacement.syncs.phone, (_) async => surfaced.add('replacement'));
    status.complete(SyncJobFetch(
        SyncJobFetchOutcome.ok,
        SyncJobStatusResponse.fromJson({
          'job_id': 'original-job',
          'status': 'completed',
          'result': {
            'new_memories': ['original-conversation'],
            'updated_memories': []
          },
        })));
    await pass;

    expect(surfaced, ['original'], reason: 'a late result must never borrow the replacement account callback');
  });

  testWidgets('On the Way clears a server-confirmed recording after startup without another upload', (tester) async {
    final wal = _uploaded('completed-after-relaunch');
    final service = _Service(
        gate,
        (id) async => SyncJobFetch(
              SyncJobFetchOutcome.ok,
              SyncJobStatusResponse.fromJson({
                'job_id': id,
                'status': 'completed',
                'result': {'new_memories': [], 'updated_memories': []},
              }),
            ));
    service.syncs.phone.testWals = [wal];
    provider = SyncProvider(
      walService: service,
      uploadGate: gate,
      waitForWalReady: (_) async {},
      startRecovery: () async {}, // Hold the real startup wake until the first frame is visible.
    );
    await provider!.initialized;
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    await tester.pumpWidget(ChangeNotifierProvider<SyncProvider>.value(
      value: provider!,
      child: MaterialApp(
        theme: buildOmiTheme(brightness: Brightness.dark),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: OnTheWayPage(pendingWork: PendingWorkStore()),
      ),
    ));
    expect(find.textContaining('on the way'), findsOneWidget);
    final l = AppLocalizations.of(tester.element(find.byType(OnTheWayPage)));

    await tester.runAsync(() => coordinator.wake(WakeTrigger.startup));
    await tester.pumpAndSettle();

    expect(find.text(l.allRecordingsSynced), findsOneWidget);
    expect(wal.status, WalStatus.synced);
    expect(service.syncs.uploads, 0);
    expect(provider!.allWals, [wal], reason: 'the recording is acknowledged, not deleted to hide the backlog');
    await tester.pumpWidget(const SizedBox.shrink());
    coordinator.dispose();
    SyncReconciler.instance.dispose();
  });
}
