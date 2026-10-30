import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

/// Identity reads go through AuthService's token gateway: FirebaseAuth in real builds, a synthetic
/// principal in the local hermetic harness. A read that went to FirebaseAuth directly would ignore
/// the harness principal (and, with no Firebase app, throw).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _Gateway gateway;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    gateway = _Gateway();
    AuthService.installLocalHarnessTokenGateway(gateway);
  });

  test('currentUser is whoever the gateway says is signed in', () {
    gateway.user = const AuthUserSnapshot(uid: 'u1', email: 'me@example.test', displayName: 'Me Person');

    final user = AuthService.instance.currentUser;

    expect(user?.uid, 'u1');
    expect(user?.email, 'me@example.test');
    expect(user?.displayName, 'Me Person');
  });

  test('currentUser is null when nobody is signed in', () {
    expect(AuthService.instance.currentUser, isNull);
  });

  group("the sign-in gate (AuthenticationProvider.isSignedIn)", () {
    late AuthenticationProvider provider;

    setUp(() => provider = AuthenticationProvider(initializeListeners: false));
    tearDown(() => provider.dispose());

    test('follows the gateway: a signed-in user passes', () {
      gateway.user = const AuthUserSnapshot(uid: 'u1');

      expect(provider.isSignedIn(), isTrue);
    });

    test('an anonymous session does not pass', () {
      gateway.user = const AuthUserSnapshot(uid: 'anon', isAnonymous: true);

      expect(provider.isSignedIn(), isFalse);
    });

    test('nobody signed in does not pass', () {
      expect(provider.isSignedIn(), isFalse);
    });
  });
}

final class _Gateway implements AuthTokenGateway {
  AuthUserSnapshot? user;

  @override
  AuthUserSnapshot? get currentUser => user;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async => user = null;
}
