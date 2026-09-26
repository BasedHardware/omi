/// The interactive device tutorial ("Speak Into Your Omi") is retired: it confused new accounts,
/// and getting Omi to know you is To do's first task now. Its code stays archived in
/// lib/pages/onboarding/interactive_device_onboarding/, and nothing else in the app may open it.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('nothing in the app opens the retired device tutorial', () {
    final opens = <String>[];
    for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
      if (!file.path.endsWith('.dart') || file.path.contains('interactive_device_onboarding/')) continue;
      if (file.readAsStringSync().contains('InteractiveDeviceOnboardingWrapper')) opens.add(file.path);
    }
    expect(opens, isEmpty, reason: 'the device tutorial is retired; see its archive note');
  });
}
