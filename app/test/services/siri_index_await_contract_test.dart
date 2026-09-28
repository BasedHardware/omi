import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Siri index writes are awaited at every Dart call site', () {
    final calls = RegExp(
      r'unawaited\s*\(\s*SiriIntegration\.(?:current|instance)\.(?:upsert\w*|reconcile\w*|delete\w*|refreshAuthoritative\w*|refreshOwnerWideIndex|wipe|setEnabled)',
      multiLine: true,
    );
    final offenders = <String>[];
    for (final file
        in Directory('lib').listSync(recursive: true).whereType<File>().where((file) => file.path.endsWith('.dart'))) {
      final source = file.readAsStringSync();
      for (final match in calls.allMatches(source)) {
        final line = '\n'.allMatches(source.substring(0, match.start)).length + 1;
        offenders.add('${file.path}:$line');
      }
    }
    expect(offenders, isEmpty,
        reason: 'Await native index calls so delete/undo and refresh/delete keep submission order.');
  });
}
