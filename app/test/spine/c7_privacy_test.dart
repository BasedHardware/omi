import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

import 'c7_registry_test.dart' show emissionPayloads;

void main() {
  test('C7 payload oracle preserves values and compares independent map instances', () {
    final expected = [
      [
        'event',
        {'enabled': true, 'count': 1}
      ]
    ];
    expect(
        emissionPayloads([
          ('event', {'enabled': true, 'count': 1})
        ]),
        expected);
    expect(
        emissionPayloads([
          ('event', {'enabled': false, 'count': 1})
        ]),
        isNot(expected));
    expect(
        emissionPayloads([
          ('wrong name', {'enabled': true, 'count': 1})
        ]),
        isNot(expected));
  });
  test('C7 generated properties reject free values and cannot carry a mutated property bag', () {
    dynamic construct = TranscribeLaterToggled.new;
    for (final value in <Object>[
      'synthetic@local.test',
      'synthetic transcript',
      '00:11:22:33:44:55',
      {'content': 'synthetic memory'},
      17,
    ]) {
      expect(() => construct(enabled: value), throwsA(isA<TypeError>()));
    }
    for (final enabled in [false, true]) {
      final event = TranscribeLaterToggled(enabled: enabled);
      expect(event.properties, {'enabled': enabled});
      event.properties['email'] = 'synthetic@local.test';
      expect(event.properties, {'enabled': enabled});
    }
    for (final event in <RegisteredEvent>[
      const OnboardingCompleted(),
      const PhoneMicRecordingStarted(),
      const PhoneMicRecordingStopped(),
    ]) {
      expect(event.properties, isEmpty);
    }
  });
}
