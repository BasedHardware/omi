import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/receipt_waiter.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ReliabilityExperiments.overrideForTesting({'receipt_long_poll'});
  });
  tearDown(() => ReliabilityExperiments.overrideForTesting(null));

  test('receipt_long_poll off (baseline): the waiter opens no request, handles no job, and the endpoint is refused',
      () async {
    ReliabilityExperiments.overrideForTesting({});
    final requests = <List<String>>[];
    final open = Completer<SyncReceiptBatch>();
    final waiter = ReceiptWaiter(
      jobs: () => {'a'},
      fetch: (ids, _) {
        requests.add(ids);
        return open.future;
      },
      apply: (_) async {},
    );
    waiter.refresh();
    await Future<void>.delayed(Duration.zero);
    expect(requests, isEmpty);
    expect(waiter.handles('a'), isFalse);
    await expectLater(waitForSyncReceipts(['a'], Completer<void>().future), throwsStateError);

    // The same waiter works once the experiment is selected.
    ReliabilityExperiments.overrideForTesting({'receipt_long_poll'});
    waiter.refresh();
    await Future<void>.delayed(Duration.zero);
    expect(requests, [
      ['a']
    ]);
    expect(waiter.handles('a'), isTrue);
    waiter.stop();
    open.complete(const SyncReceiptBatch({}, {}));
  });

  test('a newly accepted job replaces the wait; a late reply after stop is ignored', () async {
    final jobs = {'a'};
    final requests = <List<String>>[];
    final replies = <Completer<SyncReceiptBatch>>[];
    final aborted = <int>[];
    final saved = <String>{};
    final waiter = ReceiptWaiter(
      jobs: () => {...jobs},
      fetch: (ids, abort) {
        final i = requests.length;
        requests.add(ids);
        final reply = Completer<SyncReceiptBatch>();
        replies.add(reply);
        abort.then((_) => aborted.add(i));
        return reply.future;
      },
      apply: (receipts) async {
        saved.addAll(receipts.keys);
        jobs.removeAll(receipts.keys);
      },
    );
    waiter.refresh();
    jobs.add('b');
    waiter.refresh();
    await Future<void>.delayed(Duration.zero);
    expect(aborted, [0]);
    expect(requests.length, 1);
    replies[0].complete(const SyncReceiptBatch({}, {}));
    await Future<void>.delayed(Duration.zero);
    expect(requests[1], unorderedEquals(['a', 'b']));
    replies[1].complete(const SyncReceiptBatch({'b': SyncJobFetch(SyncJobFetchOutcome.ok)}, {}));
    await Future<void>.delayed(Duration.zero);
    expect(saved, {'b'});
    expect(requests[2], ['a']);
    waiter.stop();
    replies[2].complete(const SyncReceiptBatch({'a': SyncJobFetch(SyncJobFetchOutcome.ok)}, {}));
    await Future<void>.delayed(Duration.zero);
    expect(saved, {'b'});
    expect(requests.length, 3);
  });

  test('an unavailable handle yields to legacy recovery while healthy jobs continue', () async {
    final jobs = {'missing', 'fresh'};
    final selected = <List<String>>[];
    final last = Completer<SyncReceiptBatch>();
    final waiter = ReceiptWaiter(
      jobs: () => {...jobs},
      fetch: (ids, _) async {
        selected.add(ids);
        if (selected.length == 1) return const SyncReceiptBatch({}, {'missing'});
        return last.future;
      },
      apply: (_) async {},
    );
    waiter.refresh();
    await Future<void>.delayed(Duration.zero);
    expect(selected.last, ['fresh']);
    expect(waiter.handles('missing'), false);
    waiter.stop();
    last.complete(const SyncReceiptBatch({}, {}));
  });

  for (final on in [false, true]) {
    test(
        on
            ? 'receipt_finished_note on: the 16 most recently uploaded jobs take every request'
            : 'receipt_finished_note off (baseline): jobs take turns in rotation', () async {
      ReliabilityExperiments.overrideForTesting({'receipt_long_poll', if (on) 'receipt_finished_note'});
      final jobs = {for (var i = 0; i < 20; i++) 'job-${i.toString().padLeft(2, '0')}'};
      final times = {for (final id in jobs) id: 1000 + int.parse(id.substring(4))};
      final requests = <List<String>>[];
      final replies = <Completer<SyncReceiptBatch>>[];
      final waiter = ReceiptWaiter(
        jobs: () => {...jobs},
        uploadTimes: () => times,
        fetch: (ids, _) {
          requests.add(ids);
          replies.add(Completer<SyncReceiptBatch>());
          return replies.last.future;
        },
        apply: (_) async {},
      );
      waiter.refresh();
      await Future<void>.delayed(Duration.zero);
      replies[0].complete(const SyncReceiptBatch({}, {}));
      await Future<void>.delayed(Duration.zero);
      expect(requests.length, 2);
      final newest = [for (var i = 19; i >= 4; i--) 'job-${i.toString().padLeft(2, '0')}'];
      if (on) {
        expect(requests[0], newest);
        expect(requests[1], newest);
        // Every job stays the waiter's; the older four are reached by their paced status polls.
        expect(jobs.every(waiter.handles), isTrue);
      } else {
        expect(requests[0].length, 16);
        expect(requests[1], isNot(unorderedEquals(requests[0])));
      }
      waiter.stop();
      replies[1].complete(const SyncReceiptBatch({}, {}));
    });
  }
}
