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

  test('titles keep ordinary bracketed words and lose only citation-shaped units', () {
    final cases = <(String, List<String>, String)>[
      ('Project [Q3]', [], 'Project [Q3]'),
      ('Q3 Review [2024]', [], 'Q3 Review [2024]'),
      ('Notes [v2] [s01234]', [], 'Notes [v2]'),
      ('Kickoff [s01234]', ['s01234'], 'Kickoff'),
      ('Recap [abc]', ['abc'], 'Recap'),
      ('Recap [Speaker 1]', [], 'Recap'),
      ('Speaker_00 recap', [], 'recap'),
      ('Sync [443191dc-8b75-4451-9d72-27c449b9ea45]', [], 'Sync'),
      ('Plan [s01234, Q3]', [], 'Plan [s01234, Q3]'),
      ('Mixed [Q3] text s01234', ['s01234'], 'Mixed [Q3] text'),
      ('[s01234]', [], ''),
      ('Project [Q3] \uE012', [], 'Project [Q3] \uE012'),
      ('[Project [s01234]]', [], '[Project [s01234]]'),
      ('[Project [s01234] notes', [], '[Project notes'),
      ('Plan ] [Q3] [s01234', [], 'Plan ] [Q3] [s01234'),
      ('Link [x](https://e.com) [s01234]', [], 'Link [x](https://e.com)'),
    ];
    for (final (input, ids, expected) in cases) {
      expect(presentableNoteTitle(input, ids), expected, reason: input);
    }
    final many = List.filled(5000, '[Q3]').join(' ');
    expect(presentableNoteTitle('$many [s01234]', const []), many);
  });

  test('Home title repair stays bounded with a long transcript on every row', () {
    // The 1433 watchdog sampled regexp canonicalization in repairPass while
    // Home built a conversation title. Thirty ordinary mounted-row rebuilds
    // must not compile 45,000 absent-ID Unicode boundary expressions.
    final ids = List.generate(1500, (i) => '00000000-0000-4000-8000-${i.toString().padLeft(12, '0')}');
    presentableNoteTitle('Warmup', const []);
    final clock = Stopwatch()..start();
    for (var i = 0; i < 30; i++) {
      final title = 'Planning the next conversation $i';
      expect(presentableNoteTitle(title, ids), title);
    }
    clock.stop();
    // A coarse watchdog-class budget, with ample host/CI headroom. This is
    // not a phone frame-time assertion; the old path takes seconds per batch.
    expect(clock.elapsed, lessThan(const Duration(seconds: 3)));
  });

  test('literal prefilter preserves Unicode boundaries and overlapping IDs', () {
    final ids = ['a.b', 'a.b-long', 's01234'];
    expect(repairNoteCitations('Keep aXb; a.b-long; a.b.', ids).text, 'Keep aXb;;.');
    expect(repairNoteCitations('字s01234 s01234字 𐐀s01234 s01234𐐀', ids).text, '字s01234 s01234字 𐐀s01234 s01234𐐀');
    expect(repairNoteCitations('Speaker_١٢ plan [s01234]', ids).text, 'plan');
  });
}
