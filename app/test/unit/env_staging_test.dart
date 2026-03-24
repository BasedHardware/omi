import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';

/// EnvFields stub with an explicit stagingApiUrl to exercise the isTrue path.
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

  group('Env.isUsingStagingApi with explicit stagingApiUrl', () {
    test('true when override matches configured stagingApiUrl', () {
      Env.overrideApiBaseUrl('https://staging.omiapi.com/');
      expect(Env.isUsingStagingApi, isTrue);
    });

    test('true with normalisation — trailing slash and case differences', () {
      Env.overrideApiBaseUrl('https://Staging.OmiApi.com');
      expect(Env.isUsingStagingApi, isTrue);
    });

    test('false when override points to a different URL', () {
      Env.overrideApiBaseUrl('https://api.prod.example.com/');
      expect(Env.isUsingStagingApi, isFalse);
    });
  });

  group('Env.stagingApiUrl getter', () {
    test('returns explicitly configured staging URL', () {
      expect(Env.stagingApiUrl, 'https://staging.omiapi.com/');
    });
  });
}
