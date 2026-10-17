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
}
