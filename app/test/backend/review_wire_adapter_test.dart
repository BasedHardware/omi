import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;
import 'package:omi/backend/schema/review.dart';

void main() {
  test('retirement preserves the empty after state through generated wires', () {
    final change = ReviewChange.fromJson({
      'change_id': 'synthetic-retired-task',
      'kind': 'other',
      'edit_kind': 'retire_task',
      'title': 'Retire task',
      'created_at': '2026-10-15T00:00:00Z',
      'before': 'Invented duplicate obligation',
      'after': '',
    });
    expect(change!.after, '');
    expect(change.copyWith(undone: true).after, '');
  });

  test('verified applied changes preserve before after context through Undo state copies', () {
    final change = ReviewChange.fromGenerated(wire.GeneratedReviewChange.fromJson({
      'change_id': 'synthetic-verified',
      'kind': 'other',
      'edit_kind': 'spelling',
      'title': 'Spelling',
      'before': 'Qorby',
      'after': 'Qorbee',
      'created_at': '2026-10-14T12:00:00Z',
      'context': {
        'conversation_title': 'Synthetic workshop',
        'main_index': 0,
        'segments': [
          {'text': 'Qorby joined the workshop.', 'is_user': true},
        ],
      },
    }));
    final undone = change.copyWith(undone: true);
    expect(undone.editKind, 'spelling');
    expect(undone.before, 'Qorby');
    expect(undone.after, 'Qorbee');
    expect(undone.context!.main.text, 'Qorby joined the workshop.');
  });

  test('additive harness proposals decode new cleanup kinds without changing the old edit arm', () {
    final page = ReviewItemsResponse.fromGeneratedV2(wire.GeneratedReviewItemsResponseV2.fromJson({
      'items': [
        {
          'item_id': 'agent_proposal:synthetic-harness',
          'kind': 'agent_proposal',
          'title': 'Synthetic duplicate tasks',
          'created_at': '2026-10-14T12:00:00Z',
          'agent_proposal': {
            'target_label': 'Draft the invented outline.',
            'other_label': 'Prepare the invented outline.',
            'edit': {
              'kind': 'merge_tasks',
              'target': 'action_items/synthetic-one',
              'other': 'action_items/synthetic-two',
              'reason': 'Synthetic duplicate obligation.',
              'evidence': ['conversations/synthetic-source'],
              'value': 4,
            },
          },
        },
      ],
      'remaining_today': 2,
    }));
    final proposal = page.items.single.agentProposal!;
    expect(proposal.editKind, 'merge_tasks');
    expect(proposal.before, 'Draft the invented outline.');
    expect(proposal.after, 'Prepare the invented outline.');
  });

  test('generated change page retains pagination and reversible UI state', () {
    final page = ReviewChangesPage.fromGenerated(
      wire.GeneratedReviewChangesResponse.fromJson({
        'changes': [
          {
            'change_id': 'synthetic-change',
            'kind': 'rename',
            'title': 'Synthetic correction',
            'created_at': '2026-10-08T12:00:00Z',
            'undone': true,
            'refs': [
              {'type': 'conversation', 'id': 'synthetic-conversation', 'label': 'Synthetic source'},
            ],
          },
        ],
        'next_cursor': 'opaque+/cursor',
      }),
    );
    expect(page.nextCursor, 'opaque+/cursor');
    expect(page.changes.single.changeId, 'synthetic-change');
    expect(page.changes.single.undone, isTrue);
    expect(page.changes.single.kind, ReviewChangeKind.rename);
    expect(page.changes.single.refs.single.id, 'synthetic-conversation');
    expect(page.changes.single.createdAt.toUtc(), DateTime.utc(2026, 10, 8, 12));
  });

  test('generated changes reject malformed mandatory response fields', () {
    expect(() => wire.GeneratedReviewChangesResponse.fromJson({'changes': 'not a list'}), throwsFormatException);
    expect(() => wire.GeneratedReviewChange.fromJson({'change_id': 'synthetic'}), throwsFormatException);
  });

  test('generated empty review retains daily headroom', () {
    final items = ReviewItemsResponse.fromGenerated(
      wire.GeneratedReviewItemsResponse.fromJson({'items': [], 'remaining_today': 2}),
    );
    expect(items.items, isEmpty);
    expect(items.remainingToday, 2);
  });

  test('generated spelling context survives the domain adapter and remains optional', () {
    final question = {
      'item_id': 'spelling:synthetic',
      'kind': 'spelling',
      'title': 'Which spelling?',
      'created_at': '2026-10-14T12:00:00Z',
      'quote': 'UL',
      'spelling': {
        'term_id': 'synthetic',
        'options': ['UL', 'URL'],
        'allow_custom': true,
        'context': {
          'conversation_title': 'Launch planning',
          'conversation_date': '2026-10-14T12:00:00Z',
          'main_index': 0,
          'quote_start': 6,
          'quote_end': 8,
          'segments': [
            {'text': '🙂 请发 UL 给我', 'speaker_label': 'You', 'is_user': true},
          ],
        },
      },
    };
    for (final withContext in [true, false]) {
      final payload = Map<String, dynamic>.from(question);
      final spelling = Map<String, dynamic>.from(question['spelling']! as Map);
      if (!withContext) spelling.remove('context');
      payload['spelling'] = spelling;
      final result = ReviewItemsResponse.fromGeneratedV2(
        wire.GeneratedReviewItemsResponseV2.fromJson({
          'items': [payload],
          'remaining_today': 3,
        }),
      );
      expect(result.items.single.spelling!.options, ['UL', 'URL']);
      final context = result.items.single.spelling!.context;
      if (withContext) {
        expect(context!.conversationTitle, 'Launch planning');
        expect(context.main.text.substring(context.quoteStart!, context.quoteEnd!), 'UL');
        expect(context.main.isUser, isTrue);
        expect(context.conversationDate!.toUtc(), DateTime.utc(2026, 10, 14, 12));
      } else {
        expect(context, isNull);
      }
    }
  });

  test('additive memory hygiene proposals retain operation, reason and memory labels', () {
    for (final kind in ['retire_memory', 'supersede_memory']) {
      final page = ReviewItemsResponse.fromGeneratedV2(
        wire.GeneratedReviewItemsResponseV2.fromJson({
          'items': [
            {
              'item_id': 'agent_proposal:synthetic-memory',
              'kind': 'agent_proposal',
              'title': 'Synthetic memory question',
              'created_at': '2026-10-14T12:00:00Z',
              'agent_proposal': {
                'target_label': 'Lives in Toytown.',
                'other_label': 'Since January, lives in New Toytown.',
                'edit': {
                  'kind': kind,
                  'target': 'memory_items/synthetic-old',
                  'other': kind == 'supersede_memory' ? 'memory_items/synthetic-new' : '',
                  'before': '',
                  'after': '',
                  'reason': 'Synthetic newer evidence.',
                  'evidence': ['conversations/synthetic-source'],
                },
              },
            },
          ],
          'remaining_today': 2,
        }),
      );
      final proposal = page.items.single.agentProposal!;
      expect(proposal.editKind, kind);
      expect(proposal.targetLabel, 'Lives in Toytown.');
      expect(proposal.otherLabel, 'Since January, lives in New Toytown.');
      expect(proposal.reason, 'Synthetic newer evidence.');
      expect(proposal.before, 'Lives in Toytown.');
      expect(proposal.after, kind == 'supersede_memory' ? 'Since January, lives in New Toytown.' : '');
    }
  });
}
