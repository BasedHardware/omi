import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('FlutterFire pins share firebase_core 3.13 and SPM is enabled', () {
    final source = File('pubspec.yaml').readAsStringSync();

    expect(source, contains('firebase_core: 3.13.0'));
    expect(source, contains('firebase_messaging: 15.2.5'));
    expect(source, contains('firebase_crashlytics: 4.3.5'));
    expect(
      source,
      isNot(contains('enable-swift-package-manager')),
      reason: 'the temporary SPM opt-out must be removed',
    );
  });
}
