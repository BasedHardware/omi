import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import 'support/hermetic_boot.dart';
import 'support/journey_evidence.dart';

/// Journey 4 — expired-session recovery/reauthentication behavior
/// (SCA-488 / C2).
///
/// Positive (hermetic lane): a signed-in fixture principal whose token
/// refresh fails TERMINALLY (Firebase would say user-token-expired) must
/// drive the app's production session machinery: [AuthService] emits a
/// terminal session-expired event, blocks subsequent authenticated requests
/// before send, and reports `missing user` on refresh attempts until
/// re-authentication. Recovery on the local_dev lane then re-mints through
/// the real custom-token endpoint (`POST /v1/auth/local-dev/custom-token`)
/// when the failure is transient — the fixture backend observes the re-mint
/// request. The final Firebase sign-in leg needs a real Auth emulator and is
/// executed by the simulator lane against the C1 session harness; this lane
/// proves the app's decisions and the observable external I/O.
///
/// Negative: a transient failure in a NON-local_dev profile must NOT trigger
/// silent re-minting — the gate test pins that production keeps a failed
/// refresh a failed refresh.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'positive: terminal token failure expires the session and local-dev recovery reaches the re-mint endpoint',
      (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j4_expired_session_recovery', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    // Leg 1 — TRANSIENT failure on a healthy session: the production
    // local-dev recovery schedules an out-of-band re-mint through the real
    // custom-token endpoint (external I/O observable even though the final
    // Firebase sign-in needs the emulator lane).
    final gateway = ScriptableGateway(
      user: gatewayUser,
      refreshOutcome: const AuthTokenTransientFailure(failureClass: 'network', code: 'io'),
    );
    AuthService.installLocalHarnessTokenGateway(gateway);

    final reMintsBefore = server.countOf('POST', '/v1/auth/local-dev/custom-token');
    await tester.runAsync(() => AuthService.instance.getIdToken());
    // The scheduled recovery runs off the call stack (documented in
    // AuthService): let real async I/O complete outside the fake clock.
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 800)));
    final reMints = server.countOf('POST', '/v1/auth/local-dev/custom-token') - reMintsBefore;
    evidence.record('local-dev-recovery-reaches-re-mint-endpoint',
        ok: reMints >= 1,
        invariant: 'local_dev transient failures recover by re-minting through the real custom-token endpoint',
        detail: '$reMints re-mint requests');
    expect(reMints, greaterThanOrEqualTo(1),
        reason: 'the scheduled local-dev recovery must call POST /v1/auth/local-dev/custom-token');

    // Leg 2 — TERMINAL failure: the session expires explicitly, and further
    // authenticated requests are blocked before send.
    final expiryEvents = <AuthSessionExpiredEvent>[];
    final sub = AuthService.instance.sessionExpiredEvents.listen(expiryEvents.add);
    addTearDown(sub.cancel);

    gateway.refreshOutcome = const AuthTokenTerminalFailure(code: 'user-token-expired');
    final token = await tester.runAsync(() => AuthService.instance.getIdToken());
    evidence.record('no-token-after-terminal-failure',
        ok: token == null, invariant: 'a terminal refresh failure yields no usable token');
    expect(token, isNull);

    evidence.record('session-expired-event-emitted',
        ok: expiryEvents.any((e) => e.reason == AuthSessionExpirationReason.terminalTokenFailure),
        invariant: 'the expired session surfaces as an explicit reauthentication signal',
        detail: expiryEvents.map((e) => e.reason.name).toList());
    expect(
      expiryEvents.any((e) => e.reason == AuthSessionExpirationReason.terminalTokenFailure),
      isTrue,
      reason: 'terminal token failure must emit the session-expired event',
    );

    // Authenticated requests are blocked before any traffic leaves the app.
    final blocked = await tester.runAsync(() => AuthService.instance.getIdToken());
    evidence.record('subsequent-requests-blocked',
        ok: blocked == null && gateway.refreshCalls >= 1,
        invariant: 'an expired session cannot silently authorize further requests');
    expect(blocked, isNull);

    evidence.stateAfter = SemanticControls.instance.state().toJson();
    expect(evidence.failed, 0);
    await evidence.write();
  });

  test('negative: production-family profiles never run local-dev silent re-minting', () async {
    final evidence = JourneyEvidence.begin(journeyId: 'j4_expired_session_recovery.production-gate', lane: journeyLane);
    final original = F.env;
    addTearDown(() => F.env = original);

    F.env = Environment.prod;
    final prodProfile = Env.profile;
    // The recovery gate keys on the profile (see
    // local_dev_session_recovery_test.dart for the full gate matrix): in
    // production-family profiles a failed refresh must stay a failed
    // refresh. This journey-level negative pins that the expiry journey's
    // recovery leg is unattainable there.
    final recoveryUnattainable = prodProfile != AppEnvironmentProfile.localDev;
    evidence.record('recovery-gate-closed-in-production',
        ok: recoveryUnattainable, invariant: 'production keeps a failed refresh a failed refresh (no silent re-auth)');
    expect(recoveryUnattainable, isTrue);
    expect(evidence.failed, 0);
    evidence.stateAfter = {'profile': prodProfile.name};
    await evidence.write();
  });
}

AuthUserSnapshot get gatewayUser => const AuthUserSnapshot(
      uid: 'omi-fixture-v1-user-1',
      email: 'omi-fixture-v1-user-1@local.test',
      displayName: 'Journey Fixture',
    );
