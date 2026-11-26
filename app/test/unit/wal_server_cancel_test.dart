import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/sync_job_cancel.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/server_cancel_pause.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Listener implements IWalSyncListener {
  final synced = <String>[];
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) => synced.add(wal.id);
}

class _MemoryStore implements WalServerCancelStore {
  List<WalServerCancelTombstone> rows = [];
  bool failSaves = false;
  final events = <String>[];

  @override
  Future<List<WalServerCancelTombstone>> load() async => List.of(rows);

  @override
  Future<bool> save(List<WalServerCancelTombstone> tombstones) async {
    if (failSaves) return false;
    events.add('save:${tombstones.map((t) => t.jobId).join(',')}');
    rows = List.of(tombstones);
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  var now = DateTime.utc(2026, 11, 18, 12);

  setUp(() async {
    now = DateTime.utc(2026, 11, 18, 12);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    dir = await Directory.systemTemp.createTemp('wal_server_cancel_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    await dir.delete(recursive: true);
  });

  Future<Wal> uploaded(String name,
      {String jobId = 'bp_job', int offset = 0, WalStatus status = WalStatus.uploaded}) async {
    await File('${dir.path}/$name.bin').writeAsBytes([1, 2, 3, 4]);
    return Wal(
      timerStart: now.millisecondsSinceEpoch ~/ 1000 - 3600 + offset,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: status,
      storage: WalStorage.disk,
      device: 'omi',
      filePath: '$name.bin',
    )..jobId = status == WalStatus.uploaded ? jobId : null;
  }

  setUpAll(() => Env.init(_TestEnvFields()));

  group('server answer mapping', () {
    test('every server answer maps to one phone action', () async {
      Future<SyncJobCancelResult> answer(int status, String body) => cancelSyncJob(
            'bp_job',
            send: (request) async {
              expect(request.method, 'DELETE');
              expect(request.url, endsWith('v2/sync-local-files/bp_job'));
              return http.Response(body, status);
            },
          );
      Future<SyncJobCancelOutcome> outcome(int status, String body) async => (await answer(status, body)).outcome;
      expect(await outcome(200, '{"outcome":"cancelled","erasure":"complete"}'), SyncJobCancelOutcome.cancelled);
      expect(await outcome(200, '{"outcome":"cancelled","erasure":"pending"}'), SyncJobCancelOutcome.erasurePending);
      expect(await outcome(200, '{"outcome":"not_found"}'), SyncJobCancelOutcome.notFound);
      final processed = await answer(200, '{"outcome":"already_processed","conversation_ids":["c1"]}');
      expect(processed.outcome, SyncJobCancelOutcome.alreadyProcessed);
      expect(processed.conversationIds, ['c1']);
      expect(await outcome(409, '{"code":"sync_job_processing","detail":"sync_job_processing"}'),
          SyncJobCancelOutcome.retryLater);
      expect(await outcome(409, '{"code":"sync_job_not_cancellable","detail":"sync_job_not_cancellable"}'),
          SyncJobCancelOutcome.notCancellable);
      expect(await outcome(409, '{"detail":"Account busy"}'), SyncJobCancelOutcome.retryLater);
      expect(await outcome(404, ''), SyncJobCancelOutcome.notFound);
      expect(await outcome(503, '{"code":"sync_job_cancel_disabled","detail":"sync_job_cancel_disabled"}'),
          SyncJobCancelOutcome.paused);
      for (final status in [429, 500, 503]) {
        expect(await outcome(status, ''), SyncJobCancelOutcome.retryLater, reason: '$status');
      }
      expect(await outcome(200, 'not json'), SyncJobCancelOutcome.retryLater);
      expect(await outcome(200, '[]'), SyncJobCancelOutcome.retryLater);
      expect(await outcome(200, '{"outcome":"something_new"}'), SyncJobCancelOutcome.retryLater);
      expect(syncJobCancelResultFrom(const ApiFailure(ApiProblem(ApiProblemKind.transport))).outcome,
          SyncJobCancelOutcome.retryLater);
    });
  });

  test('deleting a legacy-owned uploaded recording writes the tombstone before sending it', () async {
    await SharedPreferencesUtil().saveString('uid', 'current-owner');
    final store = _MemoryStore();
    final calls = <String>[];
    late File file;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (jobId) async {
          calls.add(jobId);
          // The tombstone is durable and the local copy is already gone when the server is asked.
          expect(store.rows.map((t) => t.jobId), ['bp_job']);
          expect(store.rows.single.ownerUid, 'current-owner');
          expect(file.existsSync(), isFalse);
          return const SyncJobCancelResult(SyncJobCancelOutcome.cancelled);
        });
    final wal = await uploaded('a')
      ..ownerUid = 'legacy';
    file = File('${dir.path}/a.bin');
    sync.testWals = [wal];

    final result = await sync.deleteWal(wal);

    expect(result?.outcome, SyncJobCancelOutcome.cancelled);
    expect(calls, ['bp_job']);
    expect(store.rows, isEmpty);
    expect(sync.testWals, isEmpty);
    await sync.stop();
  });

  test('a confirmed cancel returns the upload siblings that were not deleted to local custody', () async {
    final store = _MemoryStore();
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async => const SyncJobCancelResult(SyncJobCancelOutcome.erasurePending));
    final deleted = await uploaded('a');
    final sibling = await uploaded('b', offset: 30);
    final other = await uploaded('c', jobId: 'bp_other', offset: 60);
    sync.testWals = [deleted, sibling, other];

    final result = await sync.deleteWal(deleted);

    expect(result?.outcome, SyncJobCancelOutcome.erasurePending);
    expect(sibling.status, WalStatus.miss);
    expect(sibling.jobId, isNull);
    expect(File('${dir.path}/b.bin').existsSync(), isTrue);
    expect(other.status, WalStatus.uploaded);
    // Erasure is unfinished: the tombstone stays, marked fenced, for a later call.
    expect(store.rows.single.jobId, 'bp_job');
    expect(store.rows.single.fenced, isTrue);
    await sync.stop();
  });

  test('an already transcribed recording clears the tombstone and its siblings are acknowledged by the poll', () async {
    final store = _MemoryStore();
    final listener = _Listener();
    final polled = <String>[];
    final sync = LocalWalSyncImpl(listener,
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async =>
            const SyncJobCancelResult(SyncJobCancelOutcome.alreadyProcessed, conversationIds: ['conv-1']),
        jobStatusFetcher: (jobId) async {
          polled.add(jobId);
          return SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse.fromJson({
              'job_id': jobId,
              'status': 'completed',
              'total_segments': 2,
              'processed_segments': 2,
              'successful_segments': 2,
              'result': {
                'new_memories': ['conv-1'],
                'updated_memories': [],
                'failed_segments': 0,
                'total_segments': 2
              },
            }),
          );
        });
    final deleted = await uploaded('a');
    final sibling = await uploaded('b', offset: 30);
    sync.testWals = [deleted, sibling];

    final result = await sync.deleteWal(deleted);
    expect(result?.outcome, SyncJobCancelOutcome.alreadyProcessed);
    expect(result?.conversationIds, ['conv-1']);
    expect(store.rows, isEmpty);
    expect(sibling.status, WalStatus.uploaded);

    await sync.reconcileUploadedWals();
    expect(polled, ['bp_job']);
    expect(sibling.status, WalStatus.synced);
    await sync.stop();
  });

  test('offline: the tombstone survives, the job is not polled, and a later pass finishes the cancel', () async {
    final store = _MemoryStore();
    final polled = <String>[];
    var answer = const SyncJobCancelResult(SyncJobCancelOutcome.retryLater);
    final asked = <String>[];
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (jobId) async {
          asked.add(jobId);
          return answer;
        },
        jobStatusFetcher: (jobId) async {
          polled.add(jobId);
          return const SyncJobFetch(SyncJobFetchOutcome.transient);
        });
    final deleted = await uploaded('a');
    final sibling = await uploaded('b', offset: 30);
    sync.testWals = [deleted, sibling];

    expect((await sync.deleteWal(deleted))?.outcome, SyncJobCancelOutcome.retryLater);
    expect(sync.testWals, [sibling]);
    expect(File('${dir.path}/a.bin').existsSync(), isFalse);
    expect(store.rows.single.jobId, 'bp_job');
    expect(store.rows.single.fenced, isFalse);

    // Inside the backoff window nothing is asked, and the shared job is never polled.
    await sync.reconcileUploadedWals();
    expect(asked, ['bp_job']);
    expect(polled, isEmpty);
    expect(sibling.status, WalStatus.uploaded);

    now = now.add(const Duration(days: 61));
    answer = const SyncJobCancelResult(SyncJobCancelOutcome.cancelled);
    await sync.reconcileUploadedWals();
    expect(asked, ['bp_job', 'bp_job']);
    expect(store.rows, isEmpty);
    expect(sibling.status, WalStatus.miss);
    expect(sibling.jobId, isNull);
    expect(polled, isEmpty);
    // The deleted recording is gone for good: nothing can re-upload it.
    expect(sync.testWals.map((w) => w.filePath), ['b.bin']);
    await sync.stop();
  });

  test('a failed local delete rolls back a new tombstone without cancelling the job', () async {
    final store = _MemoryStore();
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async => fail('must not ask the server after a failed local delete'));
    final wal = await uploaded('a');
    await File('${dir.path}/a.bin').delete();
    await Directory('${dir.path}/a.bin').create();
    sync.testWals = [wal];

    expect((await sync.deleteWal(wal))?.outcome, SyncJobCancelOutcome.retryLater);
    expect(store.events, ['save:bp_job', 'save:']);
    expect(store.rows, isEmpty);
    expect(sync.testWals, [wal]);
    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, 'bp_job');
    await sync.stop();
  });

  test('a fenced cancel only returns siblings, even if a delete target is still tracked', () async {
    final target = await uploaded('a');
    final sibling = await uploaded('b', offset: 30);
    await File('${dir.path}/a.bin').delete();
    await Directory('${dir.path}/a.bin').create();
    final store = _MemoryStore()
      ..rows = [
        WalServerCancelTombstone(jobId: 'bp_job', ownerUid: 'legacy', createdAt: 1, targetWalIds: {target.id})
      ];
    await SharedPreferencesUtil().saveString('uid', 'current-owner');
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        jobStatusFetcher: (_) async => fail('the delete target must stay out of status reconciliation'),
        serverCancel: (_) async => const SyncJobCancelResult(SyncJobCancelOutcome.cancelled));
    sync.testWals = [target, sibling];

    await sync.reconcileUploadedWals();

    expect(target.status, WalStatus.uploaded);
    expect(target.jobId, 'bp_job');
    expect(sibling.status, WalStatus.miss);
    expect(sibling.jobId, isNull);
    expect(store.rows.single.fenced, isTrue);
    await sync.stop();
  });

  test('a tombstone that cannot be saved keeps the recording instead of orphaning its server job', () async {
    final store = _MemoryStore()..failSaves = true;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async => fail('must not ask the server without a durable tombstone'));
    final wal = await uploaded('a');
    sync.testWals = [wal];
    expect((await sync.deleteWal(wal))?.outcome, SyncJobCancelOutcome.retryLater);
    expect(sync.testWals, [wal]);
    expect(File('${dir.path}/a.bin').existsSync(), isTrue);
    await sync.stop();
  });

  test('the server kill switch pauses the erase copy until the endpoint answers again', () async {
    ServerCancelPause.instance.reset();
    ServerCancelPause.instance.now = () => now;
    addTearDown(ServerCancelPause.instance.reset);
    final store = _MemoryStore();
    var answer = const SyncJobCancelResult(SyncJobCancelOutcome.paused);
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now, persistWals: (_) async {}, serverCancelStore: store, serverCancel: (_) async => answer);
    final wal = await uploaded('a');
    sync.testWals = [wal];
    expect((await sync.deleteWal(wal))?.outcome, SyncJobCancelOutcome.paused);
    expect(ServerCancelPause.instance.paused, isTrue);
    expect(store.rows.single.jobId, 'bp_job', reason: 'a paused cancel is retried once the switch is back on');
    // An outage says nothing about the switch.
    answer = const SyncJobCancelResult(SyncJobCancelOutcome.retryLater);
    now = now.add(const Duration(minutes: 10));
    await sync.reconcileUploadedWals();
    expect(ServerCancelPause.instance.paused, isTrue);
    // The endpoint answers again: the switch is on, and the erase copy returns.
    answer = const SyncJobCancelResult(SyncJobCancelOutcome.cancelled);
    now = now.add(const Duration(hours: 7));
    await sync.reconcileUploadedWals();
    expect(ServerCancelPause.instance.paused, isFalse);
    expect(store.rows, isEmpty);
    await sync.stop();
  });

  test('recordings that never reached the server delete locally without a server call', () async {
    final store = _MemoryStore();
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async => fail('nothing to cancel'));
    final pending = await uploaded('a', status: WalStatus.miss);
    final synced = await uploaded('b', status: WalStatus.synced, offset: 30);
    sync.testWals = [pending, synced];
    expect(await sync.deleteWal(pending), isNull);
    expect(await sync.deleteWal(synced), isNull);
    expect(sync.testWals, isEmpty);
    expect(store.events, isEmpty);
    await sync.stop();
  });

  test('another account\'s tombstone is never sent with this account\'s credentials', () async {
    await SharedPreferencesUtil().saveString('uid', 'current-owner');
    final store = _MemoryStore()
      ..rows = [
        WalServerCancelTombstone(
            jobId: 'bp_foreign', ownerUid: 'previous-owner', createdAt: now.millisecondsSinceEpoch ~/ 1000)
      ];
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        serverCancelStore: store,
        serverCancel: (_) async => fail('foreign tombstone'),
        jobStatusFetcher: (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    sync.testWals = [];
    await sync.reconcileUploadedWals();
    expect(store.rows.single.jobId, 'bp_foreign');
    await sync.stop();
  });

  test('tombstones persist across restarts in preferences', () async {
    final store = PreferencesWalServerCancelStore();
    expect(await store.load(), isEmpty);
    const tombstone = WalServerCancelTombstone(
        jobId: 'bp_job', ownerUid: 'u', createdAt: 5, attempts: 2, fenced: true, targetWalIds: {'deleted-recording'});
    expect(await store.save([tombstone]), isTrue);
    final loaded = (await PreferencesWalServerCancelStore().load()).single;
    expect(loaded.toJson(), tombstone.toJson());
  });
}
