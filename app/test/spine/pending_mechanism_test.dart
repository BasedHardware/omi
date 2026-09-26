import 'package:flutter_test/flutter_test.dart';

import '../support/spine/contract.dart';

void main() {
  test('pending executes failures and fails unexpected success', () async {
    // Mechanism self-test, not a pending builder contract.
    const package = 'MECHANISM';
    var called = false;
    await runContract(() {
      pendingContract(package);
      called = true;
      expect(1, 2);
    });
    expect(called, isTrue);
    await expectLater(runContract(() {
      pendingContract(package);
    }), throwsA(isA<TestFailure>()));
    await expectLater(runContract(() {
      pendingContract(package);
      throw StateError('broken fixture');
    }), throwsA(isA<StateError>()));
    await expectLater(runContract(() async {
      await Future<void>.value();
      expect(false, isTrue);
    }), throwsA(isA<TestFailure>()));
    await runContract(() {
      pendingContract(package);
      throw UnimplementedError('skeleton');
    });
    await runContract(() {});
    expect(() => pendingContract(package), throwsStateError);
  });
}
