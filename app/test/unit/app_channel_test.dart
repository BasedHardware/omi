import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/utils/app_channel.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(PlatformManager.initializeForLocalHarness);
  tearDown(() => Env.isTestFlight = false);

  group('resolveAppChannel', () {
    test('a TestFlight install is beta whatever the profile', () {
      for (final profile in [...AppEnvironmentProfile.values, null]) {
        expect(resolveAppChannel(isTestFlight: true, profile: profile), AppChannel.beta, reason: '$profile');
      }
    });

    test('a production-profile install outside TestFlight is store (App Store and every Play track)', () {
      expect(resolveAppChannel(isTestFlight: false, profile: AppEnvironmentProfile.production), AppChannel.store);
    });

    test('non-production profiles are beta', () {
      for (final profile in [
        AppEnvironmentProfile.mobileBeta,
        AppEnvironmentProfile.localDev,
        AppEnvironmentProfile.localProd,
      ]) {
        expect(resolveAppChannel(isTestFlight: false, profile: profile), AppChannel.beta, reason: profile.name);
      }
    });

    test('an unknown profile fails closed to store', () {
      expect(resolveAppChannel(isTestFlight: false, profile: null), AppChannel.store);
    });

    test('wire values are the ones the backend accepts', () {
      expect(AppChannel.beta.wire, 'beta');
      expect(AppChannel.store.wire, 'store');
      expect(appChannelHeader, 'X-Omi-App-Channel');
    });
  });

  group('buildHeaders', () {
    test('every API request carries the channel, and TestFlight reads as beta', () async {
      Env.isTestFlight = true;
      final beta = await buildHeaders(requireAuthCheck: false, url: 'https://api.omi.me/v1/episodes/live');
      expect(beta[appChannelHeader], 'beta');
    });

    test('the channel always has a value', () async {
      Env.isTestFlight = false;
      final headers = await buildHeaders(requireAuthCheck: false, url: 'https://api.omi.me/v1/episodes/live');
      expect(headers[appChannelHeader], anyOf('beta', 'store'));
      expect(headers[appChannelHeader], currentAppChannel().wire);
    });
  });
}
