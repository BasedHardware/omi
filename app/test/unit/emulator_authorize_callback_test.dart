import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  test('local_dev asks the backend for a JSON authorize code instead of Safari', () {
    expect(AppEnvironmentProfile.localDev.usesFirebaseAuthEmulator, isTrue);
    expect(AppEnvironmentProfile.production.usesFirebaseAuthEmulator, isFalse);

    final authorize = Uri.parse('http://192.168.1.20:8000/v1/auth/authorize').replace(
      queryParameters: {
        'provider': 'google',
        'redirect_uri': 'omi-dev://auth/callback',
        'state': 'abc',
        'code_challenge': 'challenge',
        'code_challenge_method': 'S256',
      },
    );

    expect(emulatorJsonAuthorizeUri(authorize).queryParameters['response_mode'], 'json');
  });

  test('emulator JSON authorize response rebuilds the custom-scheme callback', () {
    expect(
      emulatorAuthorizeCallbackUri(callbackScheme: 'omi-dev', body: {'code': 'auth-code', 'state': 'abc'}),
      'omi-dev://auth/callback?code=auth-code&state=abc',
    );
  });

  test('emulator JSON authorize response without a code fails closed', () {
    expect(
      () => emulatorAuthorizeCallbackUri(callbackScheme: 'omi-dev', body: {'state': 'abc'}),
      throwsA(isA<Exception>()),
    );
  });
}
