import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/providers/review_provider.dart';

Map<String, dynamic> _speakerJson(String id, {String conversationId = 'c1'}) => {
      'item_id': 'speaker:$id',
      'kind': 'speaker',
      'title': 'Who said this?',
      'quote': 'See you Friday.',
      'speaker': {
        'prompt_id': id,
        'conversation_id': conversationId,
        'conversation_title': 'Sync',
        'start': 1.5,
        'end': 8,
        'candidates': [
          {'person_id': 'p1', 'name': 'Béla', 'organization': 'Paraform'},
          {'person_id': '', 'name': 'Nobody'},
        ],
        'affected_conversation_count': 4,
        'context': [
          {'speaker_label': 'Speaker 2', 'text': 'See you Friday.', 'is_target': true},
        ],
      },
    };

Map<String, dynamic> _samePersonJson() => {
      'item_id': 'same_person:x',
      'kind': 'same_person',
      'same_person': {
        'left': {'entity_id': 'person:a', 'type': 'person', 'name': 'Béla', 'conversation_count': 6},
        'right': {
          'entity_id': 'person:b',
          'type': 'person',
          'name': 'Bela K',
          'signals': ['From contacts']
        },
        'reason': 'Same company',
      },
    };

ReviewItem _item(Map<String, dynamic> json) => ReviewItem.fromJson(json)!;

const ApiResult<OpenLoopCardsResponse> _noCards = ApiSuccess(OpenLoopCardsResponse(cards: []));

Map<String, dynamic> _proposalJson({String id = 'agent_proposal:a', String kind = 'retire_task'}) => {
      'item_id': id,
      'kind': 'agent_proposal',
      'title': 'Dream suggestion',
      'agent_proposal': {
        'target_label': 'Book the venue',
        'edit': {
          'kind': kind,
          'target': 'action_items/t1',
          'before': '',
          'after': '',
          'reason': 'A later conversation says the venue is booked.',
          'evidence': ['conversations/c2'],
        },
      },
    };

void main() {
  group('wire parsing', () {
    test('drops items with an unknown kind or a missing payload', () {
      final response = ReviewItemsResponse.fromJson({
        'items': [
          _speakerJson('a'),
          {'item_id': 'x', 'kind': 'mystery'},
          {'item_id': 'y', 'kind': 'task'},
          _samePersonJson(),
        ],
        'remaining_today': 3,
      });
      expect(response.items.map((i) => i.itemId), ['speaker:a', 'same_person:x']);
      final speaker = response.items.first.speaker!;
      expect(speaker.candidates.map((c) => c.name), ['Béla'], reason: 'a candidate without an id is dropped');
      expect(speaker.affectedConversationCount, 4);
      expect(speaker.context.single.isTarget, isTrue);
    });

    test('answers serialize to the contract shape', () {
      final task = _item({
        'item_id': 'task:c1',
        'kind': 'task',
        'task': {'candidate_id': 'c1', 'description': 'Send the SOW'},
      });
      expect(
        const ReviewAnswer.dismissTask(TaskDismissReason.notMine).toJson(task.kind),
        {
          'task': {
            'decision': 'dismiss',
            'dismiss_reason': 'not_mine',
            'edited_description': null,
            'due_at': null,
            'workstream_id': null,
          },
          'not_sure': false,
        },
      );
      expect(const ReviewAnswer.notSure().toJson(ReviewItemKind.speaker), {'not_sure': true});
      expect(
        const ReviewAnswer.samePerson(true).toJson(ReviewItemKind.samePerson),
        {
          'same_person': {'decision': 'yes'},
          'not_sure': false,
        },
      );
    });

    test('entity page keeps typed refs and a pending question', () {
      final page = EntityPageData.fromJson({
        'entity_id': 'person:a',
        'type': 'person',
        'name': 'Béla',
        'organization': {'entity_id': 'org-1', 'type': 'organization', 'name': 'Paraform'},
        'facts': [
          {
            'fact_id': 'f1',
            'text': 'Based in Budapest',
            'source': {'kind': 'screen', 'label': 'Screen'},
          },
        ],
        'pending_question': _samePersonJson(),
      })!;
      expect(page.organization!.type, EntityType.organization);
      expect(page.facts.single.sourceKind, FactSourceKind.screen);
      expect(page.pendingQuestion!.kind, ReviewItemKind.samePerson);
    });
  });

  group('Dream suggestions', () {
    test('parse from the v2 queue and drop a suggestion without a payload', () {
      final response = ReviewItemsResponse.fromJson({
        'items': [
          _proposalJson(),
          {'item_id': 'agent_proposal:empty', 'kind': 'agent_proposal'},
          {
            'item_id': 'agent_proposal:v',
            'kind': 'agent_proposal',
            'agent_proposal': {
              'target_label': '',
              'vocabulary': {'kind': 'organization', 'spelling': 'Paraform', 'aliases': [], 'evidence': []},
            },
          },
        ],
        'remaining_today': 2,
      });
      expect(response.items.map((i) => i.itemId), ['agent_proposal:a', 'agent_proposal:v']);
      final retire = response.items.first.agentProposal!;
      expect(retire.editKind, 'retire_task');
      expect(retire.targetLabel, 'Book the venue');
      expect(retire.reason, 'A later conversation says the venue is booked.');
      final term = response.items.last.agentProposal!;
      expect(term.editKind, 'vocabulary');
      expect(term.after, 'Paraform');
    });

    test('accept and dismiss serialize to the v2 contract', () {
      final item = _item(_proposalJson());
      expect(const ReviewAnswer.acceptProposal().toJson(item.kind), {
        'agent_proposal': {'decision': 'accept'},
        'not_sure': false,
      });
      expect(const ReviewAnswer.dismissProposal().toJson(item.kind), {
        'agent_proposal': {'decision': 'dismiss'},
        'not_sure': false,
      });
      expect(const ReviewAnswer.notSure().toJson(item.kind), {'not_sure': true});
    });

    test('a stale suggestion (409) stays gone and is reported as a conflict', () async {
      final item = _item(_proposalJson());
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [item], remainingToday: 1)),
        sendAnswer: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      expect(await provider.answer(item, const ReviewAnswer.acceptProposal()), isFalse);
      expect(provider.lastAnswerConflict, isTrue);
      expect(provider.items, isEmpty);
      expect(provider.remainingToday, 1, reason: 'a refused answer does not use a slot');
    });
  });

  group('ReviewProvider', () {
    test('a 404 turns the surface off; success turns it on', () async {
      final off = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
        loadOpenLoopCards: () async => _noCards,
      );
      await off.load();
      expect(off.availability, ReviewAvailability.off);

      final on = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 2)),
        loadOpenLoopCards: () async => _noCards,
      );
      await on.load();
      expect(on.availability, ReviewAvailability.on);
      expect(on.items, hasLength(1));
      expect(on.remainingToday, 2);
    });

    test('reports the release channel once per session, for store builds too', () async {
      final sent = <String>[];
      final provider = ReviewProvider(
        isEligible: () => false,
        releaseChannel: () => 'app_store',
        appBuild: () async => 12500,
        reportChannel: (channel, {appBuild}) async {
          sent.add('$channel@$appBuild');
          return const ApiFailure(ApiProblem(ApiProblemKind.notFound));
        },
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
      );
      await provider.reportReleaseChannel();
      await provider.reportReleaseChannel();
      expect(sent, ['app_store@12500']);
    });

    test('a Store build uses server availability by default', () async {
      var calls = 0;
      final provider = ReviewProvider(
        releaseChannel: () => 'app_store',
        loadItems: () async {
          calls++;
          return ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 1));
        },
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      expect(calls, 1);
      expect(provider.availability, ReviewAvailability.on);
    });

    test('a transient failure keeps the surface state and reports it', () async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.server)),
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      expect(provider.availability, ReviewAvailability.unknown);
      expect(provider.loadFailed, isTrue);
    });

    test('an answered item leaves at once and comes back when the send fails', () async {
      var succeed = false;
      final a = _item(_speakerJson('a'));
      final b = _item(_speakerJson('b'));
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [a, b], remainingToday: 2)),
        sendAnswer: (_, __) async =>
            succeed ? const ApiSuccess(1) : const ApiFailure(ApiProblem(ApiProblemKind.server)),
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();

      final failed = provider.answer(a, const ReviewAnswer.speaker(personId: 'p1'));
      expect(provider.items.map((i) => i.itemId), ['speaker:b'], reason: 'optimistic removal');
      expect(await failed, isFalse);
      expect(provider.items.map((i) => i.itemId), ['speaker:a', 'speaker:b']);
      expect(provider.remainingToday, 2);

      succeed = true;
      expect(await provider.answer(a, const ReviewAnswer.speaker(personId: 'p1')), isTrue);
      expect(provider.items.map((i) => i.itemId), ['speaker:b']);
      expect(provider.remainingToday, 1);
    });

    test('finds the question about an entity and the speaker question in a conversation', () async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(
          items: [_item(_speakerJson('a', conversationId: 'conv-9')), _item(_samePersonJson())],
          remainingToday: 2,
        )),
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      expect(provider.questionAbout('person:b')?.itemId, 'same_person:x');
      expect(provider.questionAbout('person:zzz'), isNull);
      expect(provider.speakerQuestionIn('conv-9')?.itemId, 'speaker:a');
    });

    test('playing a clip marks it playing until playback ends', () async {
      final played = <String>[];
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 1)),
        loadClip: (speaker) async => ApiSuccess(Uint8List.fromList([1, 2, 3])),
        playClip: (id, _) async {
          played.add(id);
          return true;
        },
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      await provider.togglePlay(provider.items.single);
      expect(played, ['speaker:a']);
      expect(provider.playingItemId, isNull);
    });

    test('conversation entities and projects stay empty while the surface is off', () async {
      var calls = 0;
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
        loadProjects: () async {
          calls++;
          return const ApiSuccess([]);
        },
        loadConversationEntities: (_) async {
          calls++;
          return const ApiSuccess([]);
        },
        loadOpenLoopCards: () async => _noCards,
      );
      await provider.load();
      expect(await provider.conversationEntities('c1'), isEmpty);
      await provider.loadProjects();
      expect(calls, 0);
    });

    test('open-loop cards load beside the questions and drop malformed rows', () async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 1)),
        loadOpenLoopCards: () async => ApiSuccess(OpenLoopCardsResponse.fromGeneratedWireJson({
          'cards': [
            {
              'card_id': 'ol-1',
              'date': '2026-10-26',
              'question': 'Did Maya send the vendor write-up?',
              'context_line': "From Monday's Pricing sync, due Tuesday",
            },
            {'card_id': '', 'date': '2026-10-26', 'question': 'No id'},
            {'card_id': 'ol-3', 'date': '2026-10-26'},
          ],
        })),
      );
      await provider.load();
      expect(provider.openLoopCards, hasLength(1));
      final card = provider.openLoopCards.single;
      expect(card.cardId, 'ol-1');
      expect(card.question, 'Did Maya send the vendor write-up?');
      expect(card.contextLine, "From Monday's Pricing sync, due Tuesday");
    });

    test('a cards failure keeps the questions working and the page unchanged', () async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 1)),
        loadOpenLoopCards: () async => const ApiFailure(ApiProblem(ApiProblemKind.server)),
      );
      await provider.load();
      expect(provider.loadFailed, isFalse);
      expect(provider.items, hasLength(1));
      expect(provider.openLoopCards, isEmpty);
    });

    test('the surface turning off clears the cards too', () async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [
          OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Done?'),
        ])),
      );
      await provider.load();
      expect(provider.availability, ReviewAvailability.off);
      expect(provider.openLoopCards, isEmpty, reason: 'the cards share the Review surface');
    });

    test('an answered open-loop card leaves at once and comes back when the send fails', () async {
      var succeed = false;
      const a = OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Did Maya send it?');
      const b = OpenLoopCard(cardId: 'ol-2', date: '2026-10-26', question: 'Did you file the bug?');
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [a, b])),
        sendOpenLoopAnswer: (card, action) async => succeed
            ? ApiSuccess(OpenLoopAnswerResult(cardId: card.cardId, state: action.wire))
            : const ApiFailure(ApiProblem(ApiProblemKind.server)),
      );
      await provider.load();

      final failed = provider.answerOpenLoop(a, OpenLoopAction.done);
      expect(provider.openLoopCards.map((c) => c.cardId), ['ol-2'], reason: 'optimistic removal');
      expect(await failed, OpenLoopAnswerStatus.failed);
      expect(provider.openLoopCards.map((c) => c.cardId), ['ol-1', 'ol-2'], reason: 'rollback');

      succeed = true;
      expect(await provider.answerOpenLoop(a, OpenLoopAction.done), OpenLoopAnswerStatus.saved);
      expect(provider.openLoopCards.map((c) => c.cardId), ['ol-2']);
    });

    test('a 409 open-loop answer stays gone and is a conflict for that request only', () async {
      const a = OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Did Maya send it?');
      const b = OpenLoopCard(cardId: 'ol-2', date: '2026-10-26', question: 'Did you file the bug?');
      var conflict = true;
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [a, b])),
        sendOpenLoopAnswer: (card, action) async => conflict
            ? const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409))
            : const ApiFailure(ApiProblem(ApiProblemKind.server)),
      );
      await provider.load();
      expect(
        await provider.answerOpenLoop(a, OpenLoopAction.remind),
        OpenLoopAnswerStatus.conflict,
      );
      expect(provider.openLoopCards.map((c) => c.cardId), ['ol-2'], reason: 'answered on another device; stays gone');
      // The next answer's outcome is its own: a plain failure is a failure.
      conflict = false;
      expect(await provider.answerOpenLoop(b, OpenLoopAction.done), OpenLoopAnswerStatus.failed);
    });

    test('a failed send restores only its own card, keeping concurrent successes', () async {
      const a = OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Did Maya send it?');
      const b = OpenLoopCard(cardId: 'ol-2', date: '2026-10-26', question: 'Did you file the bug?');
      const c = OpenLoopCard(cardId: 'ol-3', date: '2026-10-26', question: 'Did you ping Ann?');
      final pendingA = Completer<ApiResult<OpenLoopAnswerResult>>();
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [a, b, c])),
        sendOpenLoopAnswer: (card, action) => card.cardId == 'ol-1'
            ? pendingA.future
            : Future<ApiResult<OpenLoopAnswerResult>>.value(
                ApiSuccess(OpenLoopAnswerResult(cardId: card.cardId, state: action.wire)),
              ),
      );
      await provider.load();

      // Done on a is in flight when Done on b succeeds and leaves the list.
      final aAnswer = provider.answerOpenLoop(a, OpenLoopAction.done);
      expect(await provider.answerOpenLoop(b, OpenLoopAction.done), OpenLoopAnswerStatus.saved);
      expect(provider.openLoopCards.map((x) => x.cardId), ['ol-3']);

      pendingA.complete(const ApiFailure(ApiProblem(ApiProblemKind.server)));
      expect(await aAnswer, OpenLoopAnswerStatus.failed);
      // Only a returns, at its original position; b's committed answer is not
      // resurrected by a stale pre-tap snapshot.
      expect(provider.openLoopCards.map((x) => x.cardId), ['ol-1', 'ol-3']);
    });

    test('a failed send does not duplicate a card a concurrent reload already restored', () async {
      const a = OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Did Maya send it?');
      const b = OpenLoopCard(cardId: 'ol-2', date: '2026-10-26', question: 'Did you file the bug?');
      final pendingAnswer = Completer<ApiResult<OpenLoopAnswerResult>>();
      final pendingReload = Completer<ApiResult<OpenLoopCardsResponse>>();
      var cardsLoad = 0;
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
        loadOpenLoopCards: () => cardsLoad++ == 0
            ? Future<ApiResult<OpenLoopCardsResponse>>.value(const ApiSuccess(OpenLoopCardsResponse(cards: [a, b])))
            : pendingReload.future,
        sendOpenLoopAnswer: (card, action) async => pendingAnswer.future,
      );
      await provider.load();

      final answer = provider.answerOpenLoop(a, OpenLoopAction.done);
      final reload = provider.load();
      // The server still lists a (the answer has not landed); the reload
      // restores it while the send is in flight.
      pendingReload.complete(const ApiSuccess(OpenLoopCardsResponse(cards: [a, b])));
      await reload;
      expect(provider.openLoopCards.map((x) => x.cardId), ['ol-1', 'ol-2']);

      pendingAnswer.complete(const ApiFailure(ApiProblem(ApiProblemKind.server)));
      expect(await answer, OpenLoopAnswerStatus.failed);
      expect(provider.openLoopCards.map((x) => x.cardId), ['ol-1', 'ol-2'],
          reason: 'no duplicate of the reloaded card');
    });
  });
}
