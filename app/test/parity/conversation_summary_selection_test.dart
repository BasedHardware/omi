import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';

void main() {
  final fixture = jsonDecode(File('${_repoRoot().path}/contracts/parity/conversation_summary.json').readAsStringSync())
      as Map<String, dynamic>;

  test('legacy summary rendering repairs text without mutating stored notes or app results', () {
    final structured = Structured('Title', '');
    structured.sections = [const Section(heading: 'Decision []', bodyMarkdown: 'Approved. [s01234] []')];
    final conversation = ServerConversation(
      id: 'legacy-citations',
      appResults: [],
      createdAt: DateTime.utc(2026, 1, 1),
      structured: structured,
      transcriptSegments: [
        TranscriptSegment(
            id: 's01234',
            text: 'Approved',
            speaker: null,
            isUser: false,
            personId: null,
            start: 0,
            end: 1,
            translations: [])
      ],
    );
    final selected = ConversationSummarySelection.select(conversation);
    expect(selected.kind, ConversationSummaryKind.sections);
    expect(selected.content, '## Decision\n\nApproved.');
    // The recovered inline citation becomes the section's source, as on macOS and web.
    expect(selected.sections.single.sourceSegmentIds, ['s01234']);
    expect(conversation.structured.sections.single.bodyMarkdown, 'Approved. [s01234] []');
    expect(conversation.structured.sections.single.sourceSegmentIds ?? [], isEmpty);
    conversation.appResults.add(AppResponse('App result [] [s01234]', appId: 'custom'));
    final app = ConversationSummarySelection.select(conversation);
    expect(app.kind, ConversationSummaryKind.app);
    expect(app.content, 'App result [] [s01234]');
  });

  for (final raw in fixture['cases'] as List<dynamic>) {
    final testCase = raw as Map<String, dynamic>;
    test(testCase['id'] as String, () {
      final conversationJson = testCase['conversation'] as Map<String, dynamic>;
      final structured = Structured.fromJson(Map<String, dynamic>.from(conversationJson['structured'] as Map));
      final appResults = ((conversationJson['apps_results'] as List<dynamic>?) ?? const []).map((rawResult) {
        final result = rawResult as Map<String, dynamic>;
        return AppResponse(result['content'] as String, appId: result['app_id'] as String?);
      }).toList(growable: false);
      final conversation = ServerConversation(
        id: 'summary-contract',
        createdAt: DateTime.utc(2026, 1, 1),
        structured: structured,
        appResults: appResults,
      );

      final selected = ConversationSummarySelection.select(conversation);
      final expected = testCase['expected'] as Map<String, dynamic>;
      expect(selected.kind.name, expected['kind']);
      expect(selected.content, expected['content']);
      expect(selected.appId, expected['app_id']);
      expect(selected.resultIndex, expected['result_index']);
    });
  }
}

Directory _repoRoot() {
  var directory = Directory.current.absolute;
  for (var i = 0; i < 6; i++) {
    if (Directory('${directory.path}/contracts/parity').existsSync()) return directory;
    final parent = directory.parent;
    if (parent.path == directory.path) break;
    directory = parent;
  }
  throw StateError('contracts/parity not found above ${Directory.current.path}');
}
