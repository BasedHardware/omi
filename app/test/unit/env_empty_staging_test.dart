import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';

/// EnvFields stub with an empty-string stagingApiUrl to exercise the isEmpty path.
/// Must live in a separate test file because Env._instance is late final.
class _EmptyStagingEnvFields implements EnvFields {
  @override
  String? get stagingApiUrl => ''; // STAGING_API_URL present but empty

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
    Env.init(_EmptyStagingEnvFields());
  });

  group('Env.stagingApiUrl with empty STAGING_API_URL', () {
    test('returns null when env var is empty string', () {
      expect(Env.stagingApiUrl, isNull);
    });

    test('isStagingConfigured is false when env var is empty', () {
      expect(Env.isStagingConfigured, isFalse);
    });
  });

  group('Env.isUsingStagingApi with empty STAGING_API_URL', () {
    test('false even when override matches empty staging', () {
      Env.overrideApiBaseUrl('');
      expect(Env.isUsingStagingApi, isFalse);
    });
  });
}
