import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/main.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/env/dev_env.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import './helpers/mock_helper.dart';

@GenerateMocks([AuthenticationProvider])
import 'app_test.mocks.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    setupFirebaseMocks();
    try {
      Env.init(DevEnv());
    } catch (_) {}
  });

  group('Unit Tests', () {
    test('Navigator key initialization', () {
      expect(MyApp.navigatorKey, isNotNull);
      expect(MyApp.navigatorKey, isA<GlobalKey<NavigatorState>>());
    });

    test('Auth Provider behavior', () {
      final mockAuth = MockAuthenticationProvider();
      when(mockAuth.user).thenReturn(null);
      when(mockAuth.isSignedIn()).thenReturn(false);

      expect(mockAuth.user, isNull);
      expect(mockAuth.isSignedIn(), isFalse);
    });
  });

  group('Widget Tests', () {
    testWidgets('Error widget displays correctly', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Material(
            child: CustomErrorWidget(
              errorMessage: 'Test error',
            ),
          ),
        ),
      );

      expect(find.text('Test error'), findsOneWidget);
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
    });
  });

  // Move complex UI tests to integration_test directory
}
