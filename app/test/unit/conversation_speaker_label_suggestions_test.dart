import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';

/// The backend persists names it proposed for numbered speakers and exposes
/// accept and dismiss for them. `ServerConversation.fromGenerated` used to drop
/// the field on the floor, so every suggestion was discarded during
/// deserialization and no client could ever offer one.
Map<String, dynamic> _conversationJson({List<Map<String, dynamic>> suggestions = const []}) {
  return {
    'id': 'conv-1',
    'created_at': '2026-07-01T12:00:00.000Z',
    'structured': {'title': 'Test', 'overview': ''},
    'started_at': null,
    'finished_at': null,
    'speaker_label_suggestions': suggestions,
  };
}

void main() {
  group('ServerConversation speaker label suggestions', () {
    test('a suggestion on the wire survives deserialization', () {
      final restored = ServerConversation.fromJson(
        _conversationJson(
          suggestions: [
            {
              'speaker_id': 1,
              'person_name': 'Alex',
              'confidence': 0.6,
              'segment_ids': ['s1', 's2'],
            },
          ],
        ),
      );

      expect(restored.speakerLabelSuggestions, hasLength(1));
      final suggestion = restored.speakerLabelSuggestions.first;
      expect(suggestion.speakerId, 1);
      expect(suggestion.personName, 'Alex');
      expect(suggestion.confidence, 0.6);
      expect(suggestion.segmentIds, ['s1', 's2']);
    });

    test('several suggestions keep their order and their own speakers', () {
      final restored = ServerConversation.fromJson(
        _conversationJson(
          suggestions: [
            {'speaker_id': 2, 'person_name': 'Sam'},
            {'speaker_id': 1, 'person_name': 'Alex'},
          ],
        ),
      );

      expect(restored.speakerLabelSuggestions.map((item) => item.speakerId), [2, 1]);
      expect(restored.speakerLabelSuggestions.map((item) => item.personName), ['Sam', 'Alex']);
    });

    test('a conversation without the field parses to an empty list', () {
      final restored = ServerConversation.fromJson(_conversationJson());
      expect(restored.speakerLabelSuggestions, isEmpty);
    });

    test('suggestions survive the cache round trip', () {
      final conv = ServerConversation.fromJson(
        _conversationJson(
          suggestions: [
            {
              'speaker_id': 3,
              'person_name': 'Alex',
              'confidence': 0.42,
              'segment_ids': ['s9'],
            },
          ],
        ),
      );

      final restored = ServerConversation.fromJson(jsonDecode(jsonEncode(conv.toJson())));

      expect(restored.speakerLabelSuggestions, hasLength(1));
      expect(restored.speakerLabelSuggestions.first.speakerId, 3);
      expect(restored.speakerLabelSuggestions.first.personName, 'Alex');
      expect(restored.speakerLabelSuggestions.first.confidence, 0.42);
      expect(restored.speakerLabelSuggestions.first.segmentIds, ['s9']);
    });
  });
}
