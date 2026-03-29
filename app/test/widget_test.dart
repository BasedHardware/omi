// Minimal smoke test that verifies the test harness works without codegen.
// The original Flutter template test constructed MyApp() directly, which requires
// all codegen files (envied, firebase_options) to exist. This test avoids that
// dependency so `flutter test` works in a fresh checkout.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Smoke test — MaterialApp renders', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Text('Omi'))));
    expect(find.text('Omi'), findsOneWidget);
  });
}
