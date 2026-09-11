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
}
