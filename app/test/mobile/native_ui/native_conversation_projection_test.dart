import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/mobile/native_ui/native_conversation_projection.dart';

ServerConversation conversation({bool locked = false}) => ServerConversation(
      id: 'conversation-1',
      createdAt: DateTime.utc(2026, 10, 3),
      isLocked: locked,
      structured: Structured('Private title', 'Fallback summary'),
      appResults: [AppResponse('Canonical app summary', appId: 'summary-app')],
      transcriptSegments: [
        for (final text in ['First private segment', 'Second private segment'])
          TranscriptSegment(
            id: '',
            text: text,
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0,
            end: 1,
            translations: [],
          ),
      ],
    );

Map<String, Object?> project(ServerConversation item, {bool detail = false}) => projectNativeConversation(
      item,
      title: item.structured.title,
      timestamp: 'Localized date',
      lockedTitle: 'Locked conversation',
      speaker: (_) => 'Localized speaker',
      includeDetail: detail,
    );

void main() {
  test('list projection carries no transcript or summary payload', () {
    final result = project(conversation());
    expect(result['title'], 'Private title');
    expect(result.containsKey('summary'), isFalse);
    expect(result.containsKey('transcript'), isFalse);
    expect(result.containsKey('externalText'), isFalse);
  });

  test('native reader uses the same canonical summary as the current detail page', () {
    final result = project(conversation(), detail: true);
    expect(result['summary'], 'Canonical app summary');
    final segments = result['transcript'] as List;
    expect(segments.map((segment) => segment['text']), ['First private segment', 'Second private segment']);
    expect(segments.map((segment) => segment['speaker']).toSet(), {'Localized speaker'});
    expect(segments.map((segment) => segment['id']).toSet().length, 2);
  });

  test('locked content is stripped before crossing the native boundary', () {
    final result = project(conversation(locked: true), detail: true);
    expect(result['title'], 'Locked conversation');
    expect(result['locked'], isTrue);
    expect(result['summary'], isEmpty);
    expect(result['transcript'], isEmpty);
    expect(result['externalText'], isEmpty);
    expect(jsonEncode(result), isNot(contains('Private')));
    expect(jsonEncode(result), isNot(contains('Canonical app summary')));
  });

  test('Dart detail projection matches the fixture decoded by the Swift renderer', () {
    final snapshot = jsonDecode(File('test/fixtures/native_home_v1.json').readAsStringSync()) as Map;
    final expected = snapshot['groups'][0]['conversations'][0] as Map;
    final segments = expected['transcript'] as List;
    final item = ServerConversation(
      id: expected['id'] as String,
      createdAt: DateTime.utc(2026, 10, 3),
      structured: Structured(expected['title'] as String, expected['summary'] as String),
      starred: expected['starred'] as bool,
      transcriptSegments: [
        for (var index = 0; index < segments.length; index++)
          TranscriptSegment(
            id: 'segment-${index + 1}',
            text: segments[index]['text'] as String,
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0,
            end: 1,
            translations: [],
          ),
      ],
    );
    expect(
      projectNativeConversation(
        item,
        title: expected['title'] as String,
        timestamp: expected['timestamp'] as String,
        lockedTitle: 'Conversation',
        speaker: (index) => segments[index]['speaker'] as String,
        includeDetail: true,
      ),
      expected,
    );
  });
}
