import 'package:flutter_test/flutter_test.dart';

import '../lib/main.dart';

const _valid =
    '--omi-capture-query=polish=1&qa=chat&state=error&platform=mobile&theme=dark&width=regular&accessibility=high_contrast&locale=en-US';

void main() {
  test('capture builds accept one strict mobile fixture query', () {
    expect(
      surfaceQueryForLaunch(
        captureOnly: true,
        compileQuery: 'qa=wrong&platform=mobile',
        arguments: [_valid],
      ),
      'polish=1&qa=chat&state=error&platform=mobile&theme=dark&width=regular&accessibility=high_contrast&locale=en-US',
    );
  });

  test('production builds ignore launch capture arguments', () {
    expect(
      surfaceQueryForLaunch(
        captureOnly: false,
        compileQuery: 'route=home&platform=mobile',
        arguments: [_valid, '--omi-capture-query=polish=1&qa=tasks'],
      ),
      'route=home&platform=mobile',
    );
  });

  for (final mutation in <String, String>{
    'missing argument': '',
    'duplicate argument': 'duplicate',
    'unknown key':
        'polish=1&qa=chat&state=error&platform=mobile&theme=dark&width=regular&accessibility=none&locale=en-US&evil=1',
    'duplicate key':
        'polish=1&qa=chat&qa=tasks&state=error&platform=mobile&theme=dark&width=regular&accessibility=none&locale=en-US',
    'wrong platform':
        'polish=1&qa=chat&state=error&platform=desktop&theme=dark&width=regular&accessibility=none&locale=en-US',
    'malformed escape':
        'polish=1&qa=chat&state=error&platform=mobile&theme=dark&width=regular&accessibility=none&locale=%ZZ',
  }.entries) {
    test('capture parser rejects ${mutation.key}', () {
      final arguments = mutation.key == 'missing argument'
          ? const <String>[]
          : mutation.key == 'duplicate argument'
          ? <String>[_valid, _valid]
          : <String>['--omi-capture-query=${mutation.value}'];
      expect(
        () => surfaceQueryForLaunch(
          captureOnly: true,
          compileQuery: '',
          arguments: arguments,
        ),
        throwsFormatException,
      );
    });
  }
}
