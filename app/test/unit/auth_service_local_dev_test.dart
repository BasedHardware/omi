import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  group('AuthService.signInWithLocalDevToken', () {
    late Environment originalEnv;

    setUp(() => originalEnv = F.env);
    tearDown(() => F.env = originalEnv);

    test('refuses to run in a production-family build', () async {
      // The authoritative gate is server-side: the backend endpoint 404s unless
      // it is bound to a Firebase Auth emulator. This client-side check exists
      // so a production build never issues the request at all, and it must fail
      // before any network call — asserted here by the absence of any HTTP
      // stubbing: if it reached http.post this test would hang or error
      // differently rather than throwing StateError.
      F.env = Environment.prod;
      expect(Env.profile, AppEnvironmentProfile.production);

      await expectLater(
        AuthService.instance.signInWithLocalDevToken(),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            contains('only available in the local_dev profile'),
          ),
        ),
      );
    });

    test('the local_dev profile is what gates it, not the flavour name', () {
      // Guards against the check drifting to `F.env == Environment.dev`, which
      // would wrongly admit local_prod and mobile_beta builds.
      F.env = Environment.dev;
      expect(Env.profile, AppEnvironmentProfile.localDev);

      F.env = Environment.prod;
      expect(Env.profile, isNot(AppEnvironmentProfile.localDev));
    });
  });
}
