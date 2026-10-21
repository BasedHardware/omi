import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('location foreground start does not re-arm startForegroundService', () {
    final source = File('lib/utils/audio/foreground.dart').readAsStringSync();
    expect(source, contains('ForegroundServiceTypes.location'));
    expect(source, isNot(contains('FlutterForegroundTask.restartService')));
  });
}
