import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('failed onboarding restore resolves without throwing', () async {
    // With no Env.init, the server lookup throws before any network call.
    // AuthService swallows that failure, so restore_onboarding rarely trips
    // the boot circuit breaker even when the restore itself fails.
    expect(() => Env.apiBaseUrl, throwsA(isA<Error>()));
    await expectLater(AuthService.instance.restoreOnboardingState(), completes);
  });
}
