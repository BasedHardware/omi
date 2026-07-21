import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/environment_detector.dart';

void main() {
  test('TestFlight builds always select the beta release ring', () {
    expect(EnvironmentDetector.shouldUseBetaReleaseRing(true, betaBuild: false), isTrue);
  });

  test('Android internal build identity selects beta without TestFlight', () {
    expect(EnvironmentDetector.shouldUseBetaReleaseRing(false, betaBuild: true), isTrue);
  });

  test('store build identity remains out of the beta release ring', () {
    expect(EnvironmentDetector.shouldUseBetaReleaseRing(false, betaBuild: false), isFalse);
  });
}
