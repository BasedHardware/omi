import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';

/// Guards the blast radius of local-dev session re-minting.
///
/// The recovery path replaces a session instead of refreshing it, which is only
/// acceptable because the local harness can mint tokens on demand. In production
/// a failed refresh must stay a failed refresh: silently re-authenticating would
/// hide exactly the signal an expired or revoked session exists to give.
///
/// The recovery itself needs a live FirebaseAuth and an HTTP round trip, so what
/// is pinned here is the gate that decides whether it may run at all.
void main() {
  group('local-dev session recovery gate', () {
    late Environment originalEnv;

    setUp(() => originalEnv = F.env);
    tearDown(() => F.env = originalEnv);

    test('production-family builds are not local_dev, so recovery cannot run', () {
      F.env = Environment.prod;
      expect(Env.profile, AppEnvironmentProfile.production);
      expect(Env.profile == AppEnvironmentProfile.localDev, isFalse);
    });

    test('the dev flavour resolves to local_dev, where recovery is permitted', () {
      F.env = Environment.dev;
      expect(Env.profile, AppEnvironmentProfile.localDev);
    });

    test('the gate keys on the profile, not the flavour name', () {
      // Guards against the check drifting to `F.env == Environment.dev`, which
      // would wrongly admit any build whose profile is not local_dev.
      for (final env in Environment.values) {
        F.env = env;
        final isLocalDev = Env.profile == AppEnvironmentProfile.localDev;
        final isProductionFamily = Env.profile == AppEnvironmentProfile.production;
        expect(
          isLocalDev && isProductionFamily,
          isFalse,
          reason: 'a profile must never be both local_dev and production for env $env',
        );
      }
    });
  });
}
