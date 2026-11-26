import 'package:flutter_test/flutter_test.dart';
import 'package:omi/flavors.dart';

void main() {
  const supportedFlavors = {
    'dev': Environment.dev,
    'prod': Environment.prod,
    'raybanDat': Environment.dev,
    'PROD': Environment.prod,
  };

  for (final entry in supportedFlavors.entries) {
    test('${entry.key} selects the ${entry.value.name} environment', () {
      expect(Environment.tryFromFlavor(entry.key), entry.value);
    });
  }

  test('only supported flavors resolve to an environment', () {
    expect(Environment.tryFromFlavor(null), isNull);
    expect(Environment.tryFromFlavor(''), isNull);
    expect(Environment.tryFromFlavor('preview'), isNull);
  });
}
