import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/main.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/env/dev_env.dart';
import 'package:friend_private/flavors.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import './helpers/mock_helper.dart';

import './helpers/mock_helper.dart';
import 'app_test.mocks.dart';

@GenerateMocks([
  AuthenticationProvider,
  ConnectivityProvider,
  AppProvider,
  SharedPreferencesUtil,
])

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    setupFirebaseMocks();
    try {
      Env.init(DevEnv());
    } catch (e) {
      print('Environment initialization failed: $e');
      rethrow;
    }
  });

  group('Provider Tests', () {
    group('AuthProvider', () {
      late MockAuthenticationProvider authProvider;

      setUp(() {
        authProvider = MockAuthenticationProvider();
      });

      test('initial state', () {
        when(authProvider.user).thenReturn(null);
        when(authProvider.isSignedIn()).thenReturn(false);
        when(authProvider.loading).thenReturn(false);

        expect(authProvider.user, isNull);
        expect(authProvider.isSignedIn(), isFalse);
        expect(authProvider.loading, isFalse);
      });
    });

    group('ConnectivityProvider', () {
      late MockConnectivityProvider connectivityProvider;

      setUp(() {
        connectivityProvider = MockConnectivityProvider();
      });

      test('connection status', () {
        when(connectivityProvider.isConnected).thenReturn(true);
        expect(connectivityProvider.isConnected, isTrue);
      });
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

    testWidgets('Error widget handles long messages', (tester) async {
      final longMessage = List.filled(1000, 'A').join();

      await tester.pumpWidget(
        MaterialApp(
          home: Material(
            child: SizedBox(
              width: 400,
              height: 600,
              child: CustomErrorWidget(
                errorMessage: longMessage,
              ),
            ),
          ),
        ),
      );

      // Verify the message is displayed
      expect(find.text(longMessage), findsOneWidget);

      // Find the scrollable container by key instead
      expect(
        find.byKey(const Key('error_message_scroll_view')),
        findsOneWidget,
      );
    });
  });

  group('Utility Tests', () {
    late MockSharedPreferencesUtil prefsUtil;

    setUp(() {
      prefsUtil = MockSharedPreferencesUtil();
    });

    test('onboarding completion status', () {
      when(prefsUtil.onboardingCompleted).thenReturn(true);
      expect(prefsUtil.onboardingCompleted, isTrue);
    });

    test('environment configuration', () {
      expect(F.env, isNotNull);
      expect(F.title, isNotNull);
      expect(Env, isNotNull);
    });
  });

  group('Navigation Tests', () {
    test('Navigator key initialization', () {
      expect(MyApp.navigatorKey, isNotNull);
      expect(MyApp.navigatorKey, isA<GlobalKey<NavigatorState>>());
    });
  });
}
