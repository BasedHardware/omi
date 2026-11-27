// Reliability experiment `fast_end_feedback`: every way of ending a conversation starts the same two
// waiting requests, and each answer reaches Home and any page showing that conversation.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/coordinators/provider_capture_external_actions.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/utils/reliability_experiments.dart';

Map<String, dynamic> _row(String id, String tile, {Map<String, dynamic> extra = const {}}) => {
      'id': id,
      'created_at': '2026-11-16T10:00:00Z',
      'started_at': '2026-11-16T10:00:00Z',
      'finished_at': '2026-11-16T10:05:00Z',
      'source': 'omi',
      'status': tile == 'done' ? 'completed' : (tile == 'live' ? 'in_progress' : 'processing'),
      'kind': 'conversation',
      'tile_state': tile,
      'structured': {'title': tile == 'live' ? '' : 'Planning the next visit', 'overview': '', 'emoji': '🌳'},
      'transcript_segments': <Object>[],
      ...extra,
    };

ConversationByIdResult _read(String id, String tile) =>
    (item: ServerConversation.fromJson(_row(id, tile)), ok: true, inaccessible: false);

ApiResult<ConversationsLiveRead> _live(bool v3, {Map<String, dynamic>? conversation}) =>
    ApiSuccess(ConversationsLiveRead.fromGeneratedWireJson({'v3': v3, 'conversation': conversation}));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ConversationsV3Provider.awaitSummaryAfterEnd', () {
    test('sends the outline wait then the summary wait; each answer is published and re-reads Home', () async {
      final outline = Completer<({ConversationByIdResult result, bool settled})>();
      final summary = Completer<({ConversationByIdResult result, bool settled})>();
      final asked = <(String, bool)>[];
      var liveReads = 0;
      var rowReads = 0;
      final provider = ConversationsV3Provider(
        fetchLive: () async {
          liveReads++;
          return _live(true);
        },
        uid: () => 'u1',
        cached: 'u1:1',
        summaryWaitEnabled: () => true,
        summaryWait: (id, {untilOutline = false}) {
          asked.add((id, untilOutline));
          return untilOutline ? outline.future : summary.future;
        },
      );
      addTearDown(provider.dispose);
      final answers = <(String, ConversationTileState?, bool)>[];
      final listening = provider.summaryAnswers
          .listen((answer) => answers.add((answer.conversationId, answer.result.item!.v3?.tileState, answer.settled)));
      addTearDown(listening.cancel);

      expect(provider.awaitSummaryAfterEnd(null), isFalse, reason: 'no conversation known');
      expect(
          provider.awaitSummaryAfterEnd('c', refreshRows: () async {
            rowReads++;
          }),
          isTrue);
      expect(provider.awaitSummaryAfterEnd('c'), isFalse,
          reason: 'End from the page and the shared path name the same id');
      expect(asked, [('c', true)]);

      outline.complete((result: _read('c', 'writing'), settled: false));
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(answers, [('c', ConversationTileState.writing, false)]);
      expect((liveReads, rowReads), (1, 1));
      expect(asked, [('c', true), ('c', false)]);

      summary.complete((result: _read('c', 'done'), settled: true));
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(answers.last, ('c', ConversationTileState.done, true));
      expect((liveReads, rowReads), (2, 2));
    });

    // Reliability experiment early_title_icon: the outline answer's row goes straight to Home's list.
    for (final on in [false, true]) {
      test(
          'experiment early_title_icon ${on ? 'on: the titled outline answer is handed to Home' : 'off: no row is handed over'}',
          () async {
        if (on) ReliabilityExperiments.overrideForTesting({'early_title_icon'});
        addTearDown(() => ReliabilityExperiments.overrideForTesting(null));
        final summary = Completer<({ConversationByIdResult result, bool settled})>();
        ConversationByIdResult titled(String tile, {bool locked = true}) => (
              item: ServerConversation.fromJson(_row('c', tile, extra: {'title_locked': locked})),
              ok: true,
              inaccessible: false
            );
        var outline = titled('transcribing', locked: false);
        final provider = ConversationsV3Provider(
          fetchLive: () async => _live(true),
          uid: () => 'u1',
          cached: 'u1:1',
          summaryWaitEnabled: () => true,
          summaryWait: (id, {untilOutline = false}) async =>
              untilOutline ? (result: outline, settled: false) : await summary.future,
        );
        addTearDown(provider.dispose);
        final shown = <(String, ConversationTileState?)>[];
        void showRow(ServerConversation row) => shown.add((row.id, row.v3?.tileState));

        // Ended, but its audio is still being transcribed: the title is not fixed, nothing to show yet.
        expect(provider.awaitSummaryAfterEnd('c', showRow: showRow), isTrue);
        await Future<void>.delayed(Duration.zero);
        await Future<void>.delayed(Duration.zero);
        expect(shown, isEmpty);
        summary.complete((result: titled('done'), settled: true));
        await Future<void>.delayed(Duration.zero);
        await Future<void>.delayed(Duration.zero);
        expect(shown, isEmpty, reason: 'a stored summary is an ordinary completed row: the list read brings it');

        // Committed with its outline: title and emoji fixed, summary to come.
        outline = titled('writing');
        expect(provider.awaitSummaryAfterEnd('c', showRow: showRow), isTrue);
        await Future<void>.delayed(Duration.zero);
        await Future<void>.delayed(Duration.zero);
        expect(shown, on ? [('c', ConversationTileState.writing)] : isEmpty);
      });
    }

    test('Home\'s own bounded row refresh is used while Home is watching', () async {
      var homeRows = 0;
      var fallbackRows = 0;
      final provider = ConversationsV3Provider(
        fetchLive: () async => _live(true),
        uid: () => 'u1',
        cached: 'u1:1',
        summaryWaitEnabled: () => true,
        summaryWait: (id, {untilOutline = false}) async => (result: _read(id, 'done'), settled: true),
      );
      addTearDown(provider.dispose);
      provider.watch(refreshRows: () async {
        homeRows++;
      });
      addTearDown(provider.unwatch);
      provider.awaitSummaryAfterEnd('c', refreshRows: () async {
        fallbackRows++;
      });
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect((homeRows, fallbackRows), (1, 0));
    });

    test('off: nothing is sent', () async {
      var asked = 0;
      Future<({ConversationByIdResult result, bool settled})> wait(String id, {bool untilOutline = false}) async {
        asked++;
        return (result: _read(id, 'done'), settled: true);
      }

      final off = ConversationsV3Provider(
          fetchLive: () async => _live(true),
          uid: () => 'u1',
          cached: 'u1:1',
          summaryWaitEnabled: () => false,
          summaryWait: wait);
      addTearDown(off.dispose);
      expect(off.awaitSummaryAfterEnd('c'), isFalse);
      await Future<void>.delayed(Duration.zero);
      expect(asked, 0);
    });

    test('liveWindowIdFor names the open conversation made from a recording', () async {
      final provider = ConversationsV3Provider(
        fetchLive: () async => _live(true,
            conversation: _row('window', 'live', extra: {
              'v3_recording_ids': ['socket-recording', 'upload-recording']
            })),
        uid: () => 'u1',
        cached: 'u1:1',
      );
      addTearDown(provider.dispose);
      expect(provider.liveWindowIdFor('socket-recording'), isNull, reason: 'nothing read yet');
      await provider.refresh();
      expect(provider.liveWindowIdFor('socket-recording'), 'window');
      expect(provider.liveWindowIdFor('window'), 'window');
      expect(provider.liveWindowIdFor('another-recording'), isNull);
      expect(provider.openConversationId, 'window');
    });
  });

  group('which conversation the waits are for', () {
    String? known(String recordingId) => recordingId == 'socket-recording' ? 'window' : null;

    test('the conversation End named wins', () {
      final saved = ServerConversation.fromJson(_row('socket-recording', 'writing', extra: {'recording': true}));
      expect(ProviderCaptureExternalActions.summaryWaitTarget(saved, 'named', known), 'named');
    });

    test('a conversation in the answer is the target', () {
      final saved = ServerConversation.fromJson(_row('window', 'writing'));
      expect(ProviderCaptureExternalActions.summaryWaitTarget(saved, null, known), 'window');
    });

    test('a recording in the answer maps to the open conversation made from it, or to nothing', () {
      final recording = ServerConversation.fromJson(_row('socket-recording', 'writing', extra: {'recording': true}));
      expect(ProviderCaptureExternalActions.summaryWaitTarget(recording, null, known), 'window');
      final unknown = ServerConversation.fromJson(_row('other-recording', 'writing', extra: {'recording': true}));
      expect(ProviderCaptureExternalActions.summaryWaitTarget(unknown, null, known), isNull);
    });

    test('a recording no conversation lists yet falls back to the account\'s open conversation', () {
      // The listening session's own recording while the speech travels as uploads: the server answers
      // End with it, and the conversation it closes is the open one.
      final session = ServerConversation.fromJson(_row('session-recording', 'writing', extra: {'recording': true}));
      expect(
          ProviderCaptureExternalActions.summaryWaitTarget(session, null, known, openConversationId: 'open'), 'open');
      final listed = ServerConversation.fromJson(_row('socket-recording', 'writing', extra: {'recording': true}));
      expect(
          ProviderCaptureExternalActions.summaryWaitTarget(listed, null, known, openConversationId: 'open'), 'window');
      final conversation = ServerConversation.fromJson(_row('answered', 'writing'));
      expect(ProviderCaptureExternalActions.summaryWaitTarget(conversation, null, known, openConversationId: 'open'),
          'answered');
    });
  });
}
