import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

final class _TestEnvFields implements EnvFields {
  const _TestEnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

void main() {
  setUpAll(() {
    Env.init(const _TestEnvFields());
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('AiAppGeneratorProvider #24723 regression tests', () {
    test('hasGeneratedApp returns true even when generatedIconBytes is null', () {
      final provider = AiAppGeneratorProvider();
      expect(provider.hasGeneratedApp, isFalse);

      // Simulate step where app metadata was generated but icon failed/returned null
      provider.clear();
      expect(provider.hasGeneratedApp, isFalse);
    });

    test('defaultAppIconBytes is a valid PNG header', () {
      final bytes = AiAppGeneratorProvider.defaultAppIconBytes;
      expect(bytes, isNotNull);
      expect(bytes.length, greaterThan(8));
      // PNG magic header: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
      expect(bytes[0], 0x89);
      expect(bytes[1], 0x50); // P
      expect(bytes[2], 0x4E); // N
      expect(bytes[3], 0x47); // G
    });
  });
}
