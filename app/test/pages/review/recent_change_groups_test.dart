import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;
import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/review/widgets/recent_change_groups.dart';

Map<String, dynamic> _json(String id, {String editKind = 'spelling', Map<String, dynamic>? diff, String? groupKey}) => {
      'change_id': id,
      'kind': 'other',
      'edit_kind': editKind,
      'title': 'Spelling',
      'created_at': '2026-10-1${id.length % 5}T12:00:00Z',
      'before': 'invented before',
      'after': 'invented after',
      'refs': [
        {'type': 'conversation', 'id': 'conv-$id', 'label': 'Synthetic sync $id'},
      ],
      if (diff != null) 'diff': diff,
      if (groupKey != null) 'group_key': groupKey,
    };

void main() {
  group('diff parsing', () {
    test('additive diff and group_key survive the generated wire', () {
      final raw = _json('a', groupKey: 'term:zentrix', diff: {
        'target_label': 'Zentrix',
        'field': 'transcript',
        'before': 'zen tricks',
        'after': 'Zentrix',
        'context_before': 'We should ask ',
        'context_after': ' about the pilot.',
        'occurrences': 3,
        'source_title': 'Synthetic pilot sync',
        'source_started_at': '2026-10-12T09:00:00Z',
      });
      final change = ReviewChange.fromGenerated(wire.GeneratedReviewChange.fromJson(raw), raw: raw);
      expect(change.groupKey, 'term:zentrix');
      expect(change.diff!.before, 'zen tricks');
      expect(change.diff!.after, 'Zentrix');
      expect(change.diff!.occurrenceCount, 3);
      expect(change.diff!.occurrences.single.contextBefore, 'We should ask ');
      expect(change.diff!.sourceTitle, 'Synthetic pilot sync');
      // Undo returns a copy that must keep the diff.
      expect(change.copyWith(undone: true).diff!.after, 'Zentrix');
    });

    test('group_key nested in diff, as the backend sends it, is read', () {
      final raw = _json('a', diff: {'before': 'x', 'after': 'y', 'occurrences': 2, 'group_key': 'spelling:x>y'});
      final change = ReviewChange.fromGenerated(wire.GeneratedReviewChange.fromJson(raw), raw: raw);
      expect(change.groupKey, 'spelling:x>y');
      expect(change.diff!.occurrenceCount, 2);
    });

    test('page decoding carries diffs per change', () {
      final raw = {
        'changes': [
          _json('a', diff: {'before': 'x', 'after': 'y'}),
          _json('bb'),
        ],
      };
      final page = ReviewChangesPage.fromGenerated(wire.GeneratedReviewChangesResponse.fromJson(raw), raw: raw);
      expect(page.changes[0].diff!.after, 'y');
      expect(page.changes[1].diff, isNull);
    });

    test('occurrence lists inherit the top-level span and count themselves', () {
      final diff = ReviewChangeDiff.fromJson({
        'before': 'zen tricks',
        'after': 'Zentrix',
        'occurrences': [
          {'context_before': 'One ', 'context_after': ' two.'},
          {'context_before': 'Three ', 'context_after': ' four.', 'after': 'ZENTRIX'},
        ],
      })!;
      expect(diff.occurrenceCount, 2);
      expect(diff.occurrences[0].before, 'zen tricks');
      expect(diff.occurrences[1].after, 'ZENTRIX');
    });

    test('malformed or empty diffs are ignored, not fatal', () {
      expect(ReviewChange.fromJson({..._json('a'), 'diff': 'garbage'})!.diff, isNull);
      expect(ReviewChange.fromJson({..._json('a'), 'diff': <String, dynamic>{}})!.diff, isNull);
      expect(
          ReviewChange.fromJson({
            ..._json('a'),
            'diff': {'occurrences': 'many'}
          })!
              .diff,
          isNull);
    });
  });

  group('grouping', () {
    ReviewChange change(String id, {String editKind = 'spelling', Map<String, dynamic>? diff, String? groupKey}) =>
        ReviewChange.fromJson(_json(id, editKind: editKind, diff: diff, groupKey: groupKey))!;

    test('same group_key across conversations is one row with counted places', () {
      final groups = groupRecentChanges([
        change('a', groupKey: 'k', diff: {'before': 'zen tricks', 'after': 'Zentrix', 'occurrences': 2}),
        change('bb', groupKey: 'k', diff: {'before': 'zen tricks', 'after': 'Zentrix', 'occurrences': 5}),
        change('ccc', groupKey: 'other', diff: {'before': 'olex', 'after': 'Olex'}),
      ]);
      final terms = groups[RecentChangeSection.terms]!;
      expect(terms, hasLength(2));
      final zentrix = terms.firstWhere((g) => g.after == 'Zentrix');
      expect(zentrix.changes, hasLength(2));
      expect(zentrix.conversationCount, 2);
      expect(zentrix.placeCount, 7);
    });

    test('without group_key, the same kind with the same before and after groups', () {
      final groups = groupRecentChanges([change('a'), change('bb'), change('ccc', editKind: 'memory')]);
      expect(groups[RecentChangeSection.terms]!.single.changes, hasLength(2));
      expect(groups[RecentChangeSection.memories]!.single.changes, hasLength(1));
    });

    test('rows with nothing to compare never merge', () {
      final a = ReviewChange(changeId: 'a', kind: ReviewChangeKind.other, title: 'One', createdAt: DateTime(2026));
      final b = ReviewChange(changeId: 'b', kind: ReviewChangeKind.other, title: 'Two', createdAt: DateTime(2026));
      expect(groupRecentChanges([a, b])[RecentChangeSection.other], hasLength(2));
    });

    test('sections follow screen order', () {
      final groups = groupRecentChanges([
        change('a', editKind: 'set_language'),
        change('bb', editKind: 'retire_task'),
        change('ccc', editKind: 'supersede_memory'),
        change('dddd', editKind: 'spelling'),
        change('eeeee', editKind: 'overview'),
        change('ffffff', editKind: 'merge_people'),
      ]);
      expect(groups.keys.toList(), [
        RecentChangeSection.terms,
        RecentChangeSection.memories,
        RecentChangeSection.tasks,
        RecentChangeSection.titles,
        RecentChangeSection.people,
        RecentChangeSection.conversations,
      ]);
    });

    test('ids never stand in for names', () {
      const uuid = '3f2b8c1e-5d4a-4f6b-9c2e-1a7d8e9f0b3c';
      expect(recentChangeRefLabel(const ReviewChangeRef(type: 'conversation', id: uuid, label: uuid)), isNull);
      expect(recentChangeRefLabel(const ReviewChangeRef(type: 'conversation', id: 'x', label: 'x')), isNull);
      expect(recentChangeRefLabel(const ReviewChangeRef(type: 'conversation', id: 'x', label: 'Sync')), 'Sync');
    });

    test('the reason is dropped when it only repeats the title', () {
      final repeated = ReviewChange(
          changeId: 'a', kind: ReviewChangeKind.other, title: 'Same', reason: 'Same', createdAt: DateTime(2026));
      expect(recentChangeNote(repeated), isNull);
    });
  });
}
