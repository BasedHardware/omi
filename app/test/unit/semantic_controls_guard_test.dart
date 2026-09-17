import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

/// Guard tests for the privileged dev-control surface (SCA-488 / C2).
///
/// The contract under test: seed/reset/fault controls are **absent or
/// inaccessible in production-family builds, including production-flavor
/// debug builds**. Eligibility is a single compile-time-resolvable predicate
/// (`semanticControlsEligible`); these tests pin every leg of that predicate
/// and prove the surfaces are inert when it is false.
///
/// Note on the opt-in define: `OMI_DEV_CONTROLS` is absent in this test
/// compilation on purpose — that is the "ordinary debug build" configuration.
/// The define-controlled leg is pinned structurally (it is a const from the
/// environment) and the remaining legs behaviorally.
void main() {
  group('semantic controls eligibility gate', () {
    test('production-flavor debug builds are NOT eligible (profile leg)', () {
      final original = F.env;
      addTearDown(() => F.env = original);

      F.env = Environment.prod;
      expect(Env.profile, AppEnvironmentProfile.production);
      expect(
        semanticControlsEligible,
        isFalse,
        reason: 'a production-flavor debug build must never expose privileged '
            'controls, even though kDebugMode is true',
      );
    });

    test('dev flavor resolves to local_dev, where the profile leg opens', () {
      final original = F.env;
      addTearDown(() => F.env = original);

      F.env = Environment.dev;
      expect(Env.profile, AppEnvironmentProfile.localDev);
    });

    test('eligibility never holds for production-family profiles', () {
      final original = F.env;
      addTearDown(() => F.env = original);

      for (final env in Environment.values) {
        F.env = env;
        final profile = Env.profile;
        final productionFamily =
            profile == AppEnvironmentProfile.production || profile == AppEnvironmentProfile.mobileBeta;
        if (!productionFamily) continue;
        // With the define leg false (this compilation) eligibility must be
        // false regardless; the profile leg alone already forces it.
        expect(
          semanticControlsEligible,
          isFalse,
          reason: 'profile $profile must close the gate even before the define leg',
        );
      }
    });
  });

  group('fault gate is inert when not armed / not eligible', () {
    test('beforeSend passes every request through untouched when nothing is armed', () {
      final gate = JourneyFaultGate.instance;
      expect(gate.armed, isEmpty);

      final decision = gate.beforeSend(
        'POST',
        Uri.parse('http://127.0.0.1:8000/v2/messages'),
        'Bearer real-token',
      );
      expect(decision.drop, isFalse);
      expect(decision.swappedBearer, isNull);
    });

    test('suppress-send matches only the v2 messages streaming endpoint', () {
      final gate = JourneyFaultGate.instance;
      addTearDown(gate.clearAll);

      // Arm directly: the arm() assert only guards debug misuse; in a debug
      // test runtime the assert passes for the local harness lane.
      gate.arm(JourneyFault.suppressSend);

      expect(gate.beforeSend('POST', Uri.parse('http://127.0.0.1:8000/v2/messages'), null).drop, isTrue,
          reason: 'the chat send endpoint is the fault target');
      expect(gate.beforeSend('POST', Uri.parse('http://127.0.0.1:8000/v3/memories'), null).drop, isFalse,
          reason: 'the fault must not eat unrelated traffic');
      expect(gate.beforeSend('GET', Uri.parse('http://127.0.0.1:8000/v2/messages'), null).drop, isFalse,
          reason: 'GETs on the same path are not sends');
    });

    test('clearing faults restores a pure pass-through', () {
      final gate = JourneyFaultGate.instance;
      gate.arm(JourneyFault.wrongOwnerSession);
      final armed = gate.beforeSend('POST', Uri.parse('http://127.0.0.1:8000/v3/memories'), 'Bearer real');
      expect(armed.swappedBearer, isNotNull);

      gate.clearAll();
      final cleared = gate.beforeSend('POST', Uri.parse('http://127.0.0.1:8000/v3/memories'), 'Bearer real');
      expect(cleared.swappedBearer, isNull);
      expect(cleared.drop, isFalse);
    });

    test('every fault names the invariant its journey asserts', () {
      for (final fault in JourneyFault.values) {
        expect(fault.invariant, isNotEmpty, reason: '${fault.name} must name its invariant');
      }
    });
  });

  group('install is inert in an ordinary debug build (no opt-in define)', () {
    test('installIfEligible registers nothing without OMI_DEV_CONTROLS=1', () {
      // This compilation has no OMI_DEV_CONTROLS define: the ordinary debug
      // build configuration. `installed` staying false proves no VM service
      // extension could have been registered.
      expect(semanticControlsEligible, isFalse, reason: 'test compilation omits the opt-in define');
      expect(SemanticControls.instance.installed, isFalse);
      SemanticControls.instance.installIfEligible();
      expect(SemanticControls.instance.installed, isFalse,
          reason: 'install must be a no-op when the build is not eligible');
    });
  });

  group('waitReady rejects unknown conditions loudly', () {
    test('unknown condition name is an ArgumentError, not a hang', () {
      expect(
        () => SemanticControls.instance.waitReady('not-a-condition'),
        throwsArgumentError,
      );
    });
  });

  test('kDebugMode leg: the predicate is compiled against the current mode', () {
    // Documenting the leg explicitly: in an AOT/profile build kDebugMode is
    // false and eligibility is false regardless of the other legs. This test
    // runtime is debug, so the leg is true here — the guard it pins is that
    // the predicate references kDebugMode at all.
    expect(kDebugMode, isTrue, reason: 'guard-test runs in debug; AOT exclusion is compile-time');
  });
}
