import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/structured.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Map<String, dynamic> payload({required List<dynamic> actionItems, List<dynamic> events = const []}) {
    return {
      'title': 'Team sync',
      'overview': 'Notes from the call',
      'emoji': '',
      'category': 'other',
      'actionItems': actionItems,
      'events': events,
    };
  }

  test('an action item with an unparseable due_at does not drop the conversation', () {
    final structured = Structured.fromJson(payload(actionItems: [
      {'id': 'a1', 'description': 'Good item', 'completed': false, 'due_at': '2026-08-20T16:00:00Z'},
      {'id': 'a2', 'description': 'Garbage due date', 'completed': false, 'due_at': 'not-a-date'},
      {'id': 'a3', 'description': 'Another good item', 'completed': false},
    ]));

    expect(structured.title, 'Team sync');
    expect(structured.overview, 'Notes from the call');
    expect(structured.actionItems.map((e) => e.description), ['Good item', 'Another good item']);
  });

  test('an action item with an empty due_at is skipped the same way', () {
    final structured = Structured.fromJson(payload(actionItems: [
      {'id': 'a1', 'description': 'Kept', 'completed': false},
      {'id': 'a2', 'description': 'Dropped', 'completed': false, 'due_at': ''},
    ]));

    expect(structured.actionItems.map((e) => e.description), ['Kept']);
  });

  test('a malformed event does not drop the conversation or its action items', () {
    final structured = Structured.fromJson(payload(
      actionItems: [
        {'id': 'a1', 'description': 'Kept', 'completed': false},
      ],
      events: [
        {'title': 'Standup', 'startsAt': 'not-a-date', 'duration': 30},
      ],
    ));

    expect(structured.title, 'Team sync');
    expect(structured.actionItems.map((e) => e.description), ['Kept']);
    expect(structured.events, isEmpty);
  });

  test('an action item whose deleted flag is not a bool is skipped, not fatal', () {
    final structured = Structured.fromJson(payload(actionItems: [
      {'id': 'a1', 'description': 'Kept', 'completed': false},
      {'id': 'a2', 'description': 'Dropped', 'completed': false, 'deleted': 'yes'},
    ]));

    expect(structured.title, 'Team sync');
    expect(structured.actionItems.map((e) => e.description), ['Kept']);
  });

  test('a legacy integer timestamp event with a mistyped field is skipped, not fatal', () {
    final structured = Structured.fromJson(payload(
      actionItems: [
        {'id': 'a1', 'description': 'Kept', 'completed': false},
      ],
      events: [
        {'title': 'Standup', 'startsAt': 1700000000, 'duration': 'long'},
      ],
    ));

    expect(structured.actionItems.map((e) => e.description), ['Kept']);
    expect(structured.events, isEmpty);
  });

  test('well formed payloads still decode every item', () {
    final structured = Structured.fromJson(payload(actionItems: [
      {'id': 'a1', 'description': 'One', 'completed': false, 'due_at': '2026-08-20T16:00:00Z'},
      {'id': 'a2', 'description': 'Two', 'completed': true},
    ]));

    expect(structured.actionItems.map((e) => e.description), ['One', 'Two']);
    expect(structured.actionItems.last.completed, isTrue);
  });

  test('plain string action items are still supported', () {
    final structured = Structured.fromJson(payload(actionItems: ['Legacy string item', '']));

    expect(structured.actionItems.map((e) => e.description), ['Legacy string item']);
  });

  test('skipping invalid rows preserves stored coordinates through the cache codec', () {
    final structured = Structured.fromJson(payload(actionItems: [
      '',
      null,
      {'description': 'Invalid date', 'completed': false, 'due_at': 'bad-date'},
      {'description': 'Same description', 'completed': false},
      {'description': 'Same description', 'completed': true},
    ]));
    expect(structured.actionItems.map((item) => item.sourceIndex), [3, 4]);
    final cached = Structured.fromJson(structured.toJson());
    expect(cached.actionItems.map((item) => item.sourceIndex), [3, 4]);
    expect(cached.actionItems.map((item) => item.completed), [false, true]);
    // The coordinate is cache-only; task-write and generated wire payloads stay unchanged.
    expect(cached.actionItems.first.toJson().containsKey('_cache_source_index'), isFalse);
    expect(cached.toGenerated().toJson().toString(), isNot(contains('_cache_source_index')));
  });

  test('invalid cached coordinates skip only that row', () {
    final structured = Structured.fromJson(payload(actionItems: [
      {'description': 'Bad cache coordinate', 'completed': false, '_cache_source_index': -1},
      {'description': 'Kept', 'completed': false, '_cache_source_index': 5},
    ]));
    expect(structured.actionItems.single.description, 'Kept');
    expect(structured.actionItems.single.sourceIndex, 5);
  });

  test('fresh server rows use their array position rather than a cache-only field', () {
    final structured = Structured.fromJson({
      'title': 'Fresh server summary',
      'overview': '',
      'action_items': [
        {'description': 'Kept', 'completed': false, '_cache_source_index': 99},
      ],
    });
    expect(structured.actionItems.single.sourceIndex, 0);
  });

  test('a missing or blank emoji decodes to the neutral emoji, never the brain', () {
    final missing = Structured.fromJson({
      'title': 'Minimum row',
      'overview': '',
    });
    expect(missing.emoji, Structured.neutralEmoji);
    expect(missing.emoji, '💬');

    final blank = Structured.fromJson(payload(actionItems: const []));
    expect(blank.emoji, '💬');

    // An unset field renders deterministically instead of a random pick.
    expect(Structured('Untitled', '').getEmoji(), '💬');
  });

  test('a chosen emoji survives the decode', () {
    final structured = Structured.fromJson({
      'title': 'Pitch',
      'overview': '',
      'emoji': '🎯',
      'category': 'business',
    });
    expect(structured.getEmoji(), '🎯');
  });
}
