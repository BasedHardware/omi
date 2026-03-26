import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';

/// EnvFields stub with a custom stagingApiUrl to verify Env ignores it.
/// Must live in a separate test file because Env._instance is late final.
class _StagingEnvFields implements EnvFields {
  @override
  String? get stagingApiUrl => 'https://staging.omiapi.com/';

  @override
  String? get openAIAPIKey => null;
  @override
  String? get mixpanelProjectToken => null;
  @override
  String? get apiBaseUrl => 'https://api.prod.example.com/';
  @override
  String? get growthbookApiKey => null;
  @override
  String? get googleMapsApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  setUpAll(() {
    Env.init(_StagingEnvFields());
  });

  group('Env.stagingApiUrl is hardcoded', () {
    test('returns hardcoded URL, ignores instance value', () {
      // _StagingEnvFields.stagingApiUrl is 'https://staging.omiapi.com/'
      // but Env.stagingApiUrl is hardcoded and ignores it
      expect(Env.stagingApiUrl, 'https://api.omiapi.com/');
    });
  });

  group('Env.isUsingStagingApi', () {
    test('true when override matches hardcoded staging URL', () {
      Env.overrideApiBaseUrl('https://api.omiapi.com/');
      expect(Env.isUsingStagingApi, isTrue);
    });

    test('true with normalisation — trailing slash and case differences', () {
      Env.overrideApiBaseUrl('https://API.OmiApi.com');
      expect(Env.isUsingStagingApi, isTrue);
    });

    test('false when override points to a different URL', () {
      Env.overrideApiBaseUrl('https://api.prod.example.com/');
      expect(Env.isUsingStagingApi, isFalse);
    });
  });
}
