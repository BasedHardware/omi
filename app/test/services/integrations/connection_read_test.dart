import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/integrations/connection_read.dart';

void main() {
  testWidgets('a deadline completes even when a dependency ignores cancellation', (tester) async {
    final pending = Completer<String>();
    final read = ConnectionRead(() => pending.future, const Duration(seconds: 1));
    final error = expectLater(read.future, throwsA(isA<TimeoutException>()));
    await tester.pump(const Duration(seconds: 2));
    await error;
    pending.complete('late');
    await tester.pump();
  });
  testWidgets('dispose/cancel releases the caller and owns no remaining timer', (tester) async {
    final pending = Completer<String>();
    final read = ConnectionRead(() => pending.future, const Duration(minutes: 5));
    final error = expectLater(read.future, throwsA(isA<ConnectionReadCancelled>()));
    read.cancel();
    await tester.pump();
    await error;
    pending.complete('late');
    await tester.pump();
  });
}
