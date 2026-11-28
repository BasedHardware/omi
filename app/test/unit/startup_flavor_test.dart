import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';

void main() {
  setUp(() {
    F.env = Environment.prod;
  });

  for (final invalid in [null, '', 'preview']) {
    test('startup rejects flavor ${invalid == null ? '<missing>' : '"$invalid"'}', () {
      expect(() => F.configureForStartup(invalid), throwsStateError);
      expect(F.env, Environment.prod);
    });
  }

  test('startup applies the explicitly selected development environment', () {
    F.configureForStartup('raybanDat');
    expect(F.env, Environment.dev);
  });
}
