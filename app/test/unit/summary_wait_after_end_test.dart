// Reliability experiment `fast_end_feedback` in the app: after End, two waiting requests return the
// conversation when it is committed with its outline and when its summary is stored. Off (the baseline)
// no such request is sent.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/summary_wait_after_end.dart';
import 'package:omi/utils/reliability_experiments.dart';

Map<String, dynamic> _row(String tile) => {
      'id': 'c',
      'created_at': '2026-11-16T10:00:00Z',
      'started_at': '2026-11-16T10:00:00Z',
      'finished_at': '2026-11-16T10:05:00Z',
      'source': 'omi',
      'status': tile == 'done' ? 'completed' : (tile == 'live' ? 'in_progress' : 'processing'),
      'kind': 'conversation',
      'tile_state': tile,
      'structured': {'title': tile == 'done' ? 'Planning the next visit' : '', 'overview': '', 'emoji': '🌳'},
      'transcript_segments': [
        {'text': 'Synthetic speech.', 'start': 0.0, 'end': 4.0, 'is_user': true}
      ],
    };

ConversationByIdResult _read(String tile) =>
    (item: ServerConversation.fromJson(_row(tile)), ok: true, inaccessible: false);

void main() {
  tearDown(() => ReliabilityExperiments.overrideForTesting(null));

  group('SummaryWaitAfterEnd', () {
    test('off: End sends nothing', () async {
      ReliabilityExperiments.overrideForTesting(const {});
      var calls = 0;
      final waiter = SummaryWaitAfterEnd(
        wait: (_, {untilOutline = false}) async {
          calls++;
          return (result: _read('done'), settled: true);
        },
        apply: (_, __, {required settled}) async => fail('applied while off'),
        active: (_) => true,
      );
      expect(waiter.start('c'), isFalse);
      await Future<void>.delayed(Duration.zero);
      expect(calls, 0);
    });

    test('on: the outline answer is applied first, then the summary answer; one run per conversation', () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      final outline = Completer<({ConversationByIdResult result, bool settled})>();
      final summary = Completer<({ConversationByIdResult result, bool settled})>();
      final asked = <(String, bool)>[];
      final applied = <(ConversationTileState?, bool)>[];
      final waiter = SummaryWaitAfterEnd(
        wait: (id, {untilOutline = false}) {
          asked.add((id, untilOutline));
          return untilOutline ? outline.future : summary.future;
        },
        apply: (_, result, {required settled}) async => applied.add((result.item!.v3?.tileState, settled)),
        active: (id) => id == 'c',
      );
      expect(waiter.start(null), isFalse);
      expect(waiter.start('c'), isTrue);
      expect(waiter.start('c'), isFalse, reason: 'a second End while the first run is open');
      expect(asked, [('c', true)]);
      expect(applied, isEmpty, reason: 'nothing lands before the server answers');

      outline.complete((result: _read('writing'), settled: false));
      await Future<void>.delayed(Duration.zero);
      expect(applied, [(ConversationTileState.writing, false)]);
      expect(asked, [('c', true), ('c', false)], reason: 'the summary wait starts once the outline landed');
      expect(waiter.isWaiting('c'), isTrue);

      summary.complete((result: _read('done'), settled: true));
      await Future<void>.delayed(Duration.zero);
      expect(applied, [(ConversationTileState.writing, false), (ConversationTileState.done, true)]);
      expect(waiter.isWaiting('c'), isFalse);
    });

    test('on: an outline answer that already carries the stored summary ends the run', () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      final asked = <bool>[];
      var applied = 0;
      final waiter = SummaryWaitAfterEnd(
        wait: (_, {untilOutline = false}) async {
          asked.add(untilOutline);
          return (result: _read('done'), settled: true);
        },
        apply: (_, __, {required settled}) async => applied++,
        active: (_) => true,
      );
      waiter.start('c');
      await Future<void>.delayed(Duration.zero);
      expect(asked, [true]);
      expect(applied, 1);
    });

    test('on: a summary wait that keeps running out is repeated a bounded number of times, without re-applying',
        () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      final applied = <(ConversationTileState?, bool)>[];
      final asked = <bool>[];
      final waiter = SummaryWaitAfterEnd(
        summaryAttempts: 3,
        wait: (_, {untilOutline = false}) async {
          asked.add(untilOutline);
          return (result: _read('writing'), settled: false);
        },
        apply: (_, result, {required settled}) async => applied.add((result.item!.v3?.tileState, settled)),
        active: (_) => true,
      );
      waiter.start('c');
      await pumpEventQueue();
      expect(asked, [true, false, false, false]);
      expect(applied, [(ConversationTileState.writing, false)], reason: 'only the outline answer carried news');
      expect(waiter.isWaiting('c'), isFalse);
    });

    test('on: an End the server applies late: the outline wait is repeated while the conversation is live', () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      final applied = <(ConversationTileState?, bool)>[];
      final asked = <bool>[];
      var outlineAnswers = ['live', 'live', 'writing'];
      final waiter = SummaryWaitAfterEnd(
        heldAtLeast: Duration.zero,
        wait: (_, {untilOutline = false}) async {
          asked.add(untilOutline);
          if (untilOutline) return (result: _read(outlineAnswers.removeAt(0)), settled: false);
          return (result: _read('done'), settled: true);
        },
        apply: (_, result, {required settled}) async => applied.add((result.item!.v3?.tileState, settled)),
        active: (_) => true,
      );
      waiter.start('c');
      await pumpEventQueue();
      expect(asked, [true, true, true, false]);
      expect(applied, [(ConversationTileState.writing, false), (ConversationTileState.done, true)]);

      // Never applied by the server: the run stops after its bounded attempts, having applied nothing.
      asked.clear();
      applied.clear();
      outlineAnswers = List.filled(10, 'live', growable: true);
      final bounded = SummaryWaitAfterEnd(
        heldAtLeast: Duration.zero,
        outlineAttempts: 4,
        wait: (_, {untilOutline = false}) async {
          asked.add(untilOutline);
          return (result: _read(outlineAnswers.removeAt(0)), settled: false);
        },
        apply: (_, result, {required settled}) async => applied.add((result.item!.v3?.tileState, settled)),
        active: (_) => true,
      );
      bounded.start('c');
      await pumpEventQueue();
      expect(asked, [true, true, true, true]);
      expect(applied, isEmpty);
      expect(bounded.isWaiting('c'), isFalse);
    });

    test('on: a server that does not hold the request is asked once, not in a loop', () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      var asked = 0;
      final waiter = SummaryWaitAfterEnd(
        wait: (_, {untilOutline = false}) async {
          asked++;
          return (result: _read('live'), settled: false);
        },
        apply: (_, __, {required settled}) async => fail('a still-live answer carries no news'),
        active: (_) => true,
      );
      waiter.start('c');
      await pumpEventQueue();
      expect(asked, 1);
      expect(waiter.isWaiting('c'), isFalse);
    });

    test('on: nothing is applied to a page that moved on, or from a failed request; End can ask again', () async {
      ReliabilityExperiments.overrideForTesting({SummaryWaitAfterEnd.experiment});
      var showing = false;
      var fails = true;
      var applied = 0;
      var asked = 0;
      final waiter = SummaryWaitAfterEnd(
        wait: (_, {untilOutline = false}) async {
          asked++;
          if (fails) throw StateError('network');
          return (result: _read('done'), settled: true);
        },
        apply: (_, __, {required settled}) async => applied++,
        active: (_) => showing,
      );
      expect(waiter.start('c'), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(applied, 0);
      expect(waiter.isWaiting('c'), isFalse);

      fails = false;
      asked = 0;
      expect(waiter.start('c'), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(applied, 0, reason: 'the page shows another conversation');
      expect(asked, 1, reason: 'and no second request is sent for it');

      showing = true;
      expect(waiter.start('c'), isTrue);
      await Future<void>.delayed(Duration.zero);
      expect(applied, 1);
    });
  });

  group('waitForConversationSummary', () {
    setUp(() => Env.overrideApiBaseUrl('http://127.0.0.1/'));
    tearDown(Env.clearApiBaseUrlOverrideForTesting);

    test('200 returns the conversation; the header says whether the summary is stored', () async {
      final urls = <String>[];
      Future<http.Response?> ready(String url) async {
        urls.add(url);
        return http.Response.bytes(utf8.encode(jsonEncode(_row('done'))), 200,
            headers: {'x-omi-summary-wait': 'ready', 'content-type': 'application/json; charset=utf-8'});
      }

      final stored = await waitForConversationSummary('c', send: ready, detailRead: (_) async => fail('second read'));
      expect(urls.single, endsWith('v1/conversations/c/summary/wait?until=summary'));
      expect(stored.settled, isTrue);
      expect(stored.result.item!.structured.title, 'Planning the next visit');

      for (final header in ['outline', 'timeout']) {
        final early = await waitForConversationSummary(
          'c',
          untilOutline: true,
          send: (url) async {
            urls.add(url);
            return http.Response.bytes(utf8.encode(jsonEncode(_row('writing'))), 200,
                headers: {'x-omi-summary-wait': header, 'content-type': 'application/json; charset=utf-8'});
          },
          detailRead: (_) async => fail('second read'),
        );
        expect(urls.last, endsWith('v1/conversations/c/summary/wait?until=outline'));
        expect(early.settled, isFalse);
        expect(early.result.item!.v3?.tileState, ConversationTileState.writing);
      }
    });

    test('a server without the experiment (404) or a failed request falls back to the detail read', () async {
      for (final response in <http.Response?>[http.Response('{"detail":"Not Found"}', 404), null]) {
        var reads = 0;
        final answer = await waitForConversationSummary(
          'c',
          send: (_) async => response,
          detailRead: (id) async {
            reads++;
            return _read('writing');
          },
        );
        expect(reads, 1);
        expect(answer.settled, isFalse);
        expect(answer.result.item!.id, 'c');
      }
    });
  });
}
