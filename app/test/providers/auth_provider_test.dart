import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import '../helpers/mock_helper.dart';

@GenerateMocks([AuthenticationProvider])
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    setupFirebaseMocks();
    await Firebase.initializeApp();
  });

  group('AuthProvider Tests', () {
    late AuthenticationProvider authProvider;

    setUp(() {
      authProvider = AuthenticationProvider();
    });

    test('Initial state', () async {
      expect(authProvider.user, isNull);
      expect(authProvider.loading, isFalse);
      expect(authProvider.isSignedIn(), isFalse);

      // Wait for auth state changes to propagate
      await Future.delayed(const Duration(milliseconds: 50));
    });

    tearDown(() async {
      // Wait for any pending auth operations
      await Future.delayed(const Duration(milliseconds: 50));
    });
  });
}
