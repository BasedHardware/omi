import 'package:flutter_test/flutter_test.dart';

import 'contract.dart';

/// The pending wrapper handles awaited expectations only. Flutter framework,
/// async, fixture and teardown failures remain real failures, even when pending.
void contractWidgets(String name, Future<void> Function(WidgetTester) body) {
  testWidgets('CONTRACT: $name', (tester) async {
    await runContract(() => body(tester));
    final exception = tester.takeException();
    if (exception != null) throw exception;
  });
}
