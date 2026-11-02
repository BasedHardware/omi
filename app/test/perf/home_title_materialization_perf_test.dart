import 'dart:collection';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/note_citations.dart';

class _Materializations {
  int ids = 0;
}

// Follow lazy filters so the counter records only elements materialized into a
// list/set, rather than counting the input traversal as an allocation.
class _IDs extends IterableBase<String> {
  _IDs(this.values, this.count);
  final Iterable<String> values;
  final _Materializations count;

  @override
  Iterator<String> get iterator => values.iterator;
  @override
  Iterable<String> where(bool Function(String) test) => _IDs(values.where(test), count);
  @override
  List<String> toList({bool growable = true}) {
    final result = values.toList(growable: growable);
    count.ids += result.length;
    return result;
  }

  @override
  Set<String> toSet() {
    final result = values.toSet();
    count.ids += result.length;
    return result;
  }
}

void main() {
  test('ordinary titles do not materialize the transcript ID collection', () {
    final count = _Materializations();
    final ids = _IDs(List.generate(2000, (i) => 's${i.toString().padLeft(5, '0')}'), count);
    for (var i = 0; i < 20; i++) {
      expect(presentableNoteTitle('Ordinary title without citations', ids), 'Ordinary title without citations');
    }
    // ignore: avoid_print
    print('HOME TITLE: 20 repairs, 2000 IDs, materializedIDs=${count.ids}');
    expect(count.ids, 0);
  });

  test('lazy repair preserves arbitrary IDs and IDs exposed by an earlier repair', () {
    final cases = <(String, List<String>, String)>[
      ('Recap abc', ['abc'], 'Recap'),
      ('Recap [abc]', ['abc'], 'Recap'),
      ('Recap [a\u200bbc]', ['abc'], 'Recap'),
      ('Recap a[]bc', ['abc'], 'Recap'),
      ('Mixed [Q3] text s01234', ['s01234'], 'Mixed [Q3] text'),
      ('Keep aXb; a.b-long; a.b.', ['a.b', 'a.b-long'], 'Keep aXb;;.'),
    ];
    for (final (input, ids, expected) in cases) {
      expect(presentableNoteTitle(input, ids), expected, reason: input);
    }
    expect(repairNoteCitations('a[]bc', ['abc']).text, '');
    expect(repairNoteCitations('Fact [a\u200bbc].', ['abc']).sourceIDs, ['abc']);
  });
}
