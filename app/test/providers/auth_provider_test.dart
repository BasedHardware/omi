import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:mockito/annotations.dart';
import 'package:provider/provider.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:your_app/providers/auth_provider.dart';

// Generate mocks
@GenerateMocks([FirebaseAuth, User])
import '../../../test/providers/auth_provider_test.mocks.dart';

void main() {
  late MockFirebaseAuth mockFirebaseAuth;
  late AuthProvider authProvider;

  setUp(() {
    mockFirebaseAuth = MockFirebaseAuth();
    authProvider = AuthProvider(auth: mockFirebaseAuth);
  });

  group('AuthProvider Tests', () {
    test('initial state is unauthenticated', () {
      expect(authProvider.isAuthenticated, false);
      expect(authProvider.user, null);
    });

    test('signIn updates authentication state', () async {
      final mockUser = MockUser();
      when(mockUser.uid).thenReturn('test-uid');
      when(mockUser.email).thenReturn('test@example.com');

      when(mockFirebaseAuth.signInWithEmailAndPassword(
        email: anyNamed('email'),
        password: anyNamed('password'),
      )).thenAnswer((_) async => UserCredential(user: mockUser));

      await authProvider.signIn('test@example.com', 'password');

      expect(authProvider.isAuthenticated, true);
      expect(authProvider.user, mockUser);
    });

    test('signOut clears authentication state', () async {
      when(mockFirebaseAuth.signOut())
          .thenAnswer((_) async => {});

      await authProvider.signOut();

      expect(authProvider.isAuthenticated, false);
      expect(authProvider.user, null);
    });

    test('handles sign in errors', () async {
      when(mockFirebaseAuth.signInWithEmailAndPassword(
        email: anyNamed('email'),
        password: anyNamed('password'),
      )).thenThrow(FirebaseAuthException(code: 'user-not-found'));

      expect(
        () => authProvider.signIn('test@example.com', 'wrong-password'),
        throwsA(isA<FirebaseAuthException>()),
      );
    });
  });
}
