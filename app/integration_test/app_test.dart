import 'package:integration_test/integration_test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/main.dart';
import 'package:flutter/material.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Full App Tests', () {
    testWidgets('App shows onboarding flow', (tester) async {
      await tester.pumpWidget(const MyApp());
      await tester.pumpAndSettle();

      // Test full app flow with real dependencies
      expect(find.byType(DeciderWidget), findsOneWidget);
    });
  });
}
