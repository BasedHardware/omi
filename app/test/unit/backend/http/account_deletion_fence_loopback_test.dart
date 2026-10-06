import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

import '../../../../integration_test/journeys/support/hermetic_boot.dart';

/// Nik's bug end to end over real loopback HTTP: after deleting the account and
/// signing in again, every request is answered with the deletion fence. The
/// real `HomeProvider` → `getUserPrimaryLanguage()` → pooled HTTP client path
/// must end the session (reason `accountDeleted`) instead of treating the 403
/// as "no language yet" and forcing a language sheet whose save then fails.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const fenceBody = '{"detail": {"code": "account_deletion_in_progress", "status": "failed", "retryable": false}}';

  testWidgets('GET /v1/users/language answered by the deletion fence signs the account out, once', (tester) async {
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    server.failNext('GET', '/v1/users/language', status: 403, body: fenceBody);
    server.failNext('PATCH', '/v1/users/language', status: 403, body: fenceBody);

    final events = <AuthSessionExpiredEvent>[];
    final sub = AuthService.instance.sessionExpiredEvents.listen(events.add);
    addTearDown(sub.cancel);
    expect(AuthService.instance.isSignedIn(), isTrue, reason: 'fixture principal starts signed in');

    final home = HomeProvider();
    addTearDown(home.dispose);
    await tester.runAsync(() => home.setupUserPrimaryLanguage());

    expect(server.countOf('GET', '/v1/users/language'), 1);
    expect(events.map((e) => e.reason), [AuthSessionExpirationReason.accountDeleted]);
    expect(events.single.code, 'failed', reason: 'the wipe status rides along for telemetry');
    expect(home.hasSetPrimaryLanguage, isFalse);
    expect(AuthService.instance.isSignedIn(), isFalse, reason: 'the session is over, not merely languageless');

    // The save the old forced sheet would have attempted: still a 403 upstream,
    // but the session was already expired exactly once.
    final saved = await tester.runAsync(() => setUserPrimaryLanguage('en'));
    expect(saved, isNull);
    expect(events, hasLength(1));

    // An expired session blocks the next authenticated request before send.
    final before = server.countOf('GET', '/v1/users/language');
    await tester.runAsync(() => getUserPrimaryLanguage());
    expect(server.countOf('GET', '/v1/users/language'), before);
  });

  testWidgets('a languageless account that is NOT being deleted stays signed in', (tester) async {
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    server.failNext('GET', '/v1/users/language', status: 200, body: '{"language": null}');

    final events = <AuthSessionExpiredEvent>[];
    final sub = AuthService.instance.sessionExpiredEvents.listen(events.add);
    addTearDown(sub.cancel);

    final home = HomeProvider();
    addTearDown(home.dispose);
    await tester.runAsync(() => home.setupUserPrimaryLanguage());

    expect(home.hasSetPrimaryLanguage, isFalse);
    expect(events, isEmpty);
    expect(AuthService.instance.isSignedIn(), isTrue);
  });
}
