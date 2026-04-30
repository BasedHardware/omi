import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/companion/companion_signals.dart';

void main() {
  test('CompanionSignals copyWith preserves untouched fields', () {
    const a = CompanionSignals(preferredName: 'Matheus', language: 'en');
    final b = a.copyWith(language: 'pt-BR');
    expect(b.preferredName, 'Matheus');
    expect(b.language, 'pt-BR');
  });
}
