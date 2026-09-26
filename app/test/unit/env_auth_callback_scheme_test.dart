import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';

void main() {
  // #19244: a preview build on the production servers returned through omi://, which the App
  // Store app also registers; OMI_AUTH_CALLBACK_SCHEME gives it a scheme of its own.
  test('without the define, sign-in returns through the profile scheme', () {
    expect(Env.resolveAuthCallbackScheme('', AppEnvironmentProfile.production), 'omi');
    expect(Env.resolveAuthCallbackScheme('', AppEnvironmentProfile.mobileBeta), 'omi-beta');
    expect(Env.resolveAuthCallbackScheme('', AppEnvironmentProfile.localDev), 'omi-dev');
  });

  test('OMI_AUTH_CALLBACK_SCHEME overrides the profile scheme', () {
    expect(Env.resolveAuthCallbackScheme('omi-beta', AppEnvironmentProfile.production), 'omi-beta');
  });
}
