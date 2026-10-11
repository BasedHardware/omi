import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('UI call sites submit index writes without awaiting Spotlight', () {
    final calls = RegExp(
      r'await\s+SiriIntegration\.(?:current|instance)\.(?:upsert\w*|reconcile\w*|delete\w*|refreshAuthoritative\w*|refreshOwnerWideIndex)',
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
        reason: 'UI state must use the ordered Siri queue and finish independently of Spotlight.');
  });
}
