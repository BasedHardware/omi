import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';

Map<String, dynamic> _structuredJson() => {
      'title': 'Sprint sync',
      'overview': 'Short compatibility paragraph.',
      'emoji': '🧠',
      'category': 'business',
      'sections': [
        {
          'heading': 'Decisions',
          'body_markdown': '- Ship the **beta** on Friday',
          'source_segment_ids': ['seg-1', 'seg-2'],
        },
        {
          'heading': 'Risks',
          'body_markdown': 'Backend migration is not started yet.',
          'source_segment_ids': <String>[],
        },
      ],
    };

void main() {
  group('Structured sections', () {
    test('fromJson decodes the wire sections field', () {
      final structured = Structured.fromJson(_structuredJson());

      expect(structured.sections, hasLength(2));
      expect(structured.sections.first.heading, 'Decisions');
      expect(structured.sections.first.bodyMarkdown, '- Ship the **beta** on Friday');
      expect(structured.sections.first.sourceSegmentIds, ['seg-1', 'seg-2']);
      expect(structured.sections.last.heading, 'Risks');
    });

    test('sections survive the toJson round trip', () {
      final structured = Structured.fromJson(_structuredJson());

      final restored = Structured.fromJson(jsonDecode(jsonEncode(structured.toJson())));

      expect(restored.sections, hasLength(2));
      expect(restored.sections.first.heading, 'Decisions');
      expect(restored.sections.first.bodyMarkdown, '- Ship the **beta** on Friday');
      expect(restored.sections.first.sourceSegmentIds, ['seg-1', 'seg-2']);
      expect(restored.sections.last.bodyMarkdown, 'Backend migration is not started yet.');
    });

    test('fromGenerated carries sections over from the wire model', () {
      final generated = wire.GeneratedStructured.fromJson(_structuredJson());

      final structured = Structured.fromGenerated(generated);

      expect(structured.sections, hasLength(2));
      expect(structured.sections.first.heading, 'Decisions');
    });

    test('sections survive a full conversation cache round trip', () {
      final conversation = ServerConversation(
        id: 'conv-sections',
        createdAt: DateTime.utc(2026, 7, 1, 12, 0, 0),
        structured: Structured.fromJson(_structuredJson()),
      );

      final restored = ServerConversation.fromJson(jsonDecode(jsonEncode(conversation.toJson())));

      expect(restored.structured.sections, hasLength(2));
      expect(restored.structured.sections.first.heading, 'Decisions');
      expect(restored.structured.sections.last.bodyMarkdown, 'Backend migration is not started yet.');
    });

    test('missing sections decode to an empty list', () {
      final json = _structuredJson()..remove('sections');

      expect(Structured.fromJson(json).sections, isEmpty);
    });
  });
}
