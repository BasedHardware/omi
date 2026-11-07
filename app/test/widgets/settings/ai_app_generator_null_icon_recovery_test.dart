import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
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
      provider.updateName('Test app');
      provider.updateDescription('Test description');
      expect(provider.generatedIconBytes, isNull);
      expect(provider.hasGeneratedApp, isTrue);
    });

    test('defaultAppIconBytes is a valid PNG header', () async {
      final bytes = await AiAppGeneratorProvider.getDefaultAppIconBytes();
      expect(bytes, isNotNull);
      expect(bytes.length, greaterThan(8));
      // PNG magic header: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
      expect(bytes[0], 0x89);
      expect(bytes[1], 0x50); // P
      expect(bytes[2], 0x4E); // N
      expect(bytes[3], 0x47); // G
      expect(bytes[4], 0x0D);
      expect(bytes[5], 0x0A);
      expect(bytes[6], 0x1A);
      expect(bytes[7], 0x0A);
    });
  });

  group('AddAppProvider validation #24723 regression tests', () {
    AddAppProvider buildSeededProvider() {
      final provider = AddAppProvider(
        deleteApiKeyServerFn: (_, __) async => true,
        listApiKeysServerFn: (_) async => const [],
      );
      provider.imageUrl = 'https://example.com/logo.png';
      provider.appCategory = 'productivity-and-organization';
      provider.appNameController.text = 'Test App';
      provider.appDescriptionController.text = 'Test description';
      return provider;
    }

    test('multi-capability external_integration + chat validates both capabilities regardless of order', () {
      final extCap = AppCapability(id: 'external_integration', title: 'External Integration');
      final chatCap = AppCapability(id: 'chat', title: 'Chat');

      for (final caps in [
        [extCap, chatCap],
        [chatCap, extCap],
      ]) {
        final provider = buildSeededProvider();
        provider.selectedCapabilities = List.of(caps);
        provider.sourceCodeUrlController.text = 'https://github.com/BasedHardware/omi';

        // Chat valid, external_integration missing trigger and actions -> invalid
        provider.chatPromptController.text = 'You are a helpful assistant.';
        expect(provider.isFormValid(), isFalse);
        expect(provider.validateForm(), isFalse);

        // External integration valid via trigger + webhook, chat prompt missing -> invalid
        provider.chatPromptController.clear();
        provider.triggerEvent = 'memory_created';
        provider.webhookUrlController.text = 'https://example.com/webhook';
        expect(provider.isFormValid(), isFalse);
        expect(provider.validateForm(), isFalse);

        // Both capabilities satisfied -> valid
        provider.chatPromptController.text = 'You are a helpful assistant.';
        expect(provider.isFormValid(), isTrue);
        expect(provider.validateForm(), isTrue);
      }
    });

    test('paid plan + chat requires both valid chat prompt and payment plan + price', () {
      final provider = buildSeededProvider();
      provider.selectedCapabilities = [AppCapability(id: 'chat', title: 'Chat')];
      provider.chatPromptController.text = 'Helpful assistant prompt';
      provider.isPaid = true;

      // Missing payment plan and price -> invalid
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);

      // Payment plan set but price empty -> invalid
      provider.selectePaymentPlan = 'monthly_recurring';
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);

      // Payment plan and price set -> valid
      provider.priceController.text = '9.99';
      expect(provider.isFormValid(), isTrue);
      expect(provider.validateForm(), isTrue);

      // Clearing chat prompt while paid plan is valid -> invalid
      provider.chatPromptController.clear();
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);
    });

    test('external_integration allows actions without trigger event or requires webhook when trigger event is set', () {
      final provider = buildSeededProvider();
      provider.selectedCapabilities = [AppCapability(id: 'external_integration', title: 'External Integration')];
      provider.sourceCodeUrlController.text = 'https://github.com/BasedHardware/omi';

      // Neither triggerEvent nor actions -> invalid
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);

      // Actions alone (triggerEvent == null) -> valid without webhook URL
      provider.addSpecificAction('create_memories');
      expect(provider.isFormValid(), isTrue);
      expect(provider.validateForm(), isTrue);

      // Setting triggerEvent requires a non-empty webhook URL
      provider.setTriggerEvent('memory_created');
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);

      provider.webhookUrlController.text = 'https://example.com/webhook';
      expect(provider.isFormValid(), isTrue);
      expect(provider.validateForm(), isTrue);
    });

    test('capability matching prioritizes non-empty id over colliding title', () {
      final provider = buildSeededProvider();
      // Custom backend capability whose title happens to be "Chat" but id is distinct
      final customCap = AppCapability(id: 'custom_discussion', title: 'Chat');
      provider.selectedCapabilities = [customCap];

      expect(provider.isCapabilitySelectedById('chat'), isFalse);
      expect(provider.isCapabilitySelectedById('custom_discussion'), isTrue);
      // Should not require chatPromptController since id is not 'chat'
      expect(provider.isFormValid(), isTrue);
      expect(provider.validateForm(), isTrue);

      // Empty id falls back to title matching
      final legacyTitleOnlyCap = AppCapability(id: '', title: 'Chat');
      provider.selectedCapabilities = [legacyTitleOnlyCap];
      expect(provider.isCapabilitySelectedById('chat'), isTrue);
      expect(provider.isFormValid(), isFalse);
      expect(provider.validateForm(), isFalse);
    });
  });
}
