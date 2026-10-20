import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/note_citations.dart';

void main() {
  final contract =
      jsonDecode(File('../contracts/note_citation_contract.json').readAsStringSync()) as Map<String, dynamic>;
  final knownIDs = (contract['known_ids'] as List).cast<String>();
  for (final item in contract['cases'] as List) {
    test(item['name'] as String, () {
      final ids = (item['known_ids'] as List?)?.cast<String>() ?? knownIDs;
      final result = repairNoteCitations(item['input'] as String, ids);
      expect(result.text, item['output']);
      expect(result.sourceIDs, item['source_ids']);
      expect(repairNoteCitations(result.text, ids).text, item['output']);
    });
  }

  test('a transcript segment without an id never rewrites the note', () {
    // An id-less segment arrives as '' (TranscriptSegment.fromGenerated). As a known id it would
    // match at every position between two non-word characters and the cleanup would then eat the
    // whitespace around each match: nested-list indents, hard breaks, the space after a heading
    // marker and after inline code or links.
    const input = '## Decisions\n\n- Fact. [s01234]\n  - Nested detail.\nHard break.  \nNext line.';
    final result = repairNoteCitations(input, ['', 's01234']);
    expect(result.text, '## Decisions\n\n- Fact.\n  - Nested detail.\nHard break.  \nNext line.');
    expect(result.sourceIDs, ['s01234']);
  });

  test('thousands of protected units restore exactly, including code nested in a link', () {
    // Keys used to grow with the unit count and restore once per unit: quadratic.
    final many = List.generate(3000, (i) => '`c$i` [s01234]').join(' ');
    final kept = List.generate(3000, (i) => '`c$i`').join(' ');
    expect(repairNoteCitations(many, ['s01234']).text, kept);
    final nested = repairNoteCitations('See [`x`](https://e.com) [s01234].', ['s01234']);
    expect(nested.text, 'See [`x`](https://e.com).');
    expect(nested.sourceIDs, ['s01234']);
  });
}
