import 'package:flutter_test/flutter_test.dart';
import 'package:friend_private/providers/auth_provider.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';

@GenerateMocks([AuthenticationProvider])
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AuthProvider Tests', () {
    late AuthenticationProvider authProvider;

    setUp(() {
      authProvider = AuthenticationProvider();
    });

    test('Initial state', () {
      expect(authProvider.user, isNull);
      expect(authProvider.loading, isFalse);
      expect(authProvider.hasError, isFalse);
      expect(authProvider.errorMessage, isEmpty);
    });

    test('Sign out clears user state', () async {
      await authProvider.signOut();
      expect(authProvider.user, isNull);
      expect(authProvider.loading, isFalse);
    });
  });
}
