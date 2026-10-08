import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
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

  group('ReviewProvider', () {
    test('a 404 turns the surface off; success turns it on', () async {
      final off = ReviewProvider(loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)));
      await off.load();
      expect(off.availability, ReviewAvailability.off);

      final on = ReviewProvider(
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 2)),
      );
      await on.load();
      expect(on.availability, ReviewAvailability.on);
      expect(on.items, hasLength(1));
      expect(on.remainingToday, 2);
    });

    test('a transient failure keeps the surface state and reports it', () async {
      final provider = ReviewProvider(loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.server)));
      await provider.load();
      expect(provider.availability, ReviewAvailability.unknown);
      expect(provider.loadFailed, isTrue);
    });

    test('an answered item leaves at once and comes back when the send fails', () async {
      var succeed = false;
      final a = _item(_speakerJson('a'));
      final b = _item(_speakerJson('b'));
      final provider = ReviewProvider(
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [a, b], remainingToday: 2)),
        sendAnswer: (_, __) async =>
            succeed ? const ApiSuccess(1) : const ApiFailure(ApiProblem(ApiProblemKind.server)),
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
        loadItems: () async => ApiSuccess(ReviewItemsResponse(
          items: [_item(_speakerJson('a', conversationId: 'conv-9')), _item(_samePersonJson())],
          remainingToday: 2,
        )),
      );
      await provider.load();
      expect(provider.questionAbout('person:b')?.itemId, 'same_person:x');
      expect(provider.questionAbout('person:zzz'), isNull);
      expect(provider.speakerQuestionIn('conv-9')?.itemId, 'speaker:a');
    });

    test('playing a clip marks it playing until playback ends', () async {
      final played = <String>[];
      final provider = ReviewProvider(
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [_item(_speakerJson('a'))], remainingToday: 1)),
        loadClip: (speaker) async => ApiSuccess(Uint8List.fromList([1, 2, 3])),
        playClip: (id, _) async {
          played.add(id);
          return true;
        },
      );
      await provider.load();
      await provider.togglePlay(provider.items.single);
      expect(played, ['speaker:a']);
      expect(provider.playingItemId, isNull);
    });

    test('conversation entities and projects stay empty while the surface is off', () async {
      var calls = 0;
      final provider = ReviewProvider(
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
        loadProjects: () async {
          calls++;
          return const ApiSuccess([]);
        },
        loadConversationEntities: (_) async {
          calls++;
          return const ApiSuccess([]);
        },
      );
      await provider.load();
      expect(await provider.conversationEntities('c1'), isEmpty);
      await provider.loadProjects();
      expect(calls, 0);
    });
  });
}
