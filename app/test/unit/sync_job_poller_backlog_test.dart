import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

class _MemoryStore implements SyncJobMissingStore {
  Map<String, int> data = {};
  int saves = 0;
  @override
  Map<String, int> load() => Map.of(data);
  @override
  void save(Map<String, int> firstMissingEpochMs) {
    saves++;
    data = Map.of(firstMissingEpochMs);
  }
}

Future<SyncJobFetch> _missing(String _) async => const SyncJobFetch(SyncJobFetchOutcome.notFound);

void main() {
  late DateTime now;
  late SyncRateLimiter limiter;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    limiter = SyncRateLimiter.instance;
    limiter.clear();
    now = DateTime(2026, 10, 19, 12);
    limiter.clockForTesting = () => now;
  });

  tearDown(() {
    limiter.clear();
    limiter.clockForTesting = null;
  });

  test('a first 404 survives a restart and a later process confirms it', () async {
    final store = _MemoryStore();
    final first = SyncJobPoller(clock: () => now, missingStore: store);
    expect((await first.fetch('dead', _missing)).outcome, SyncJobFetchOutcome.transient);
    expect(store.data.keys, ['dead']);

    // New process: in-memory state is gone, the observation is not.
    now = now.add(const Duration(hours: 3));
    final second = SyncJobPoller(clock: () => now, missingStore: store);
    expect((await second.fetch('dead', _missing)).outcome, SyncJobFetchOutcome.notFound);
    expect(store.data, isEmpty, reason: 'confirmed handles leave the durable set');
    expect(() => second.validateOwner(UploadFilesResult.queued('dead')), throwsA(isA<SyncRateLimitedException>()));
  });

  test('fetch provenance distinguishes a missing confirmation, a local deferral and a network transient', () async {
    final poller = SyncJobPoller(clock: () => now);
    final first = await poller.fetch('missing', _missing);
    expect(first.outcome, SyncJobFetchOutcome.transient);
    expect(first.pollAdmitted, isTrue);
    expect(first.missingConfirmationPending, isTrue);
    final deferred = await poller.fetch('missing', _missing);
    expect(deferred.pollAdmitted, isFalse);
    expect(deferred.missingConfirmationPending, isFalse);
    final network = await poller.fetch('network', (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    expect(network.pollAdmitted, isTrue);
    expect(network.missingConfirmationPending, isFalse);
  });

  test('confirmation still needs five minutes, even across processes', () async {
    final store = _MemoryStore();
    await SyncJobPoller(clock: () => now, missingStore: store).fetch('dead', _missing);
    now = now.add(const Duration(minutes: 4));
    final restarted = SyncJobPoller(clock: () => now, missingStore: store);
    expect((await restarted.fetch('dead', _missing)).outcome, SyncJobFetchOutcome.transient);
    now = now.add(const Duration(minutes: 1));
    expect((await restarted.fetch('dead', _missing)).outcome, SyncJobFetchOutcome.notFound);
  });

  test('a successful read clears a stale first 404', () async {
    final store = _MemoryStore();
    final poller = SyncJobPoller(clock: () => now, missingStore: store);
    await poller.fetch('flaky', _missing);
    now = now.add(const Duration(minutes: 6));
    await poller.fetch(
      'flaky',
      (id) async => SyncJobFetch(SyncJobFetchOutcome.ok, SyncJobStatusResponse(jobId: id, status: 'processing')),
    );
    expect(store.data, isEmpty);
    now = now.add(const Duration(minutes: 6));
    expect(
      (await poller.fetch('flaky', _missing)).outcome,
      SyncJobFetchOutcome.transient,
      reason: 'a 404 after a success starts a new confirmation window',
    );
  });

  test('observations older than the retention window are dropped', () async {
    final store = _MemoryStore()..data = {'ancient': now.subtract(const Duration(days: 8)).millisecondsSinceEpoch};
    final poller = SyncJobPoller(clock: () => now, missingStore: store);
    expect((await poller.fetch('ancient', _missing)).outcome, SyncJobFetchOutcome.transient);
  });

  test('fresh uploads are not starved by a lexically-earlier dead backlog', () {
    final poller = SyncJobPoller(clock: () => now, missingStore: _MemoryStore());
    final nowSeconds = now.millisecondsSinceEpoch ~/ 1000;
    final oldSeconds = nowSeconds - 5 * 24 * 3600;
    final uploaded = <String, int>{
      for (var i = 0; i < 2000; i++) '0${i.toString().padLeft(39, '0')}': oldSeconds + i,
      'bp_fresh_a': nowSeconds - 60,
      'bp_fresh_b': nowSeconds - 30,
    };
    final order = poller.ordered(uploaded.keys, uploadedAtSeconds: uploaded);
    expect(order.take(4), containsAll(['bp_fresh_a', 'bp_fresh_b']));
    expect(order.first, 'bp_fresh_b', reason: 'newest upload first among never-polled recent jobs');
    expect(order[1].startsWith('0'), isTrue, reason: 'old handles alternate with recent ones');
  });

  test('handles ready to confirm are admitted before any new first poll', () async {
    final store = _MemoryStore();
    final poller = SyncJobPoller(clock: () => now, missingStore: store);
    await poller.fetch('dead-z', _missing);
    now = now.add(const Duration(minutes: 10));
    final restarted = SyncJobPoller(clock: () => now, missingStore: store);
    final nowSeconds = now.millisecondsSinceEpoch ~/ 1000;
    final uploaded = {
      'dead-z': nowSeconds - 6 * 86400,
      'aaa-never-polled': nowSeconds - 6 * 86400,
      'bp_new': nowSeconds,
    };
    expect(restarted.ordered(uploaded.keys, uploadedAtSeconds: uploaded).first, 'dead-z');
  });

  test('callers without upload times keep oldest-due-first order', () {
    final poller = SyncJobPoller(clock: () => now);
    poller.defer('later', 60000);
    expect(poller.ordered(['later', 'b', 'a']), ['a', 'b', 'later']);
  });

  test('pass batches honor budget, transient backoff, server hints and missing confirmation', () async {
    final poller = SyncJobPoller(clock: () => now);
    final jobs = List.generate(100, (i) => 'job-${i.toString().padLeft(3, '0')}');
    expect(poller.dueForPass(jobs), hasLength(SyncJobPoller.maxRequestsPerMinute));
    await poller.fetch(jobs[0], (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    await poller.fetch(jobs[1], _missing);
    await poller.fetch(
      jobs[2],
      (id) async => SyncJobFetch(
        SyncJobFetchOutcome.ok,
        SyncJobStatusResponse(jobId: id, status: 'processing', pollAfterMs: 90000),
      ),
    );
    final remainder = poller.dueForPass(jobs);
    expect(remainder, hasLength(SyncJobPoller.maxRequestsPerMinute - 3));
    expect(remainder, isNot(anyOf(contains(jobs[0]), contains(jobs[1]), contains(jobs[2]))));
    for (final id in remainder) {
      await poller.fetch(id, (_) async => const SyncJobFetch(SyncJobFetchOutcome.transient));
    }
    expect(poller.dueForPass(jobs), isEmpty);
    now = now.add(const Duration(minutes: 1));
    final retry = poller.dueForPass(jobs.take(3));
    expect(retry, [jobs[0]], reason: 'transient backoff elapsed, but missing confirmation and server hint have not');
    limiter.markLimited(retryAfterSeconds: 120, reason: RateLimitReason.edgeThrottle);
    expect(poller.dueForPass(jobs), isEmpty);
  });
}
