import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';

// Builds a free, private "conversation prompt template" style app.
App _buildApp() => App.fromJson({
      'id': 'app_123',
      'name': 'My Template',
      'author': 'Jane',
      'description': 'A test template',
      'image': 'https://img/logo.png',
      'category': 'productivity-and-organization',
      'capabilities': ['memories'],
      'memory_prompt': 'Summarize the conversation',
      'private': true,
      'is_paid': false,
      'price': 0.0,
      'thumbnails': <String>[],
    });

// Seeds the provider so its form state matches [app] exactly (mirrors prepareUpdate
// without the network calls), so hasDataChanged should report no changes.
void _seedMatching(AddAppProvider p, App app) {
  p.appNameController.text = app.name;
  p.appDescriptionController.text = app.description;
  p.conversationPromptController.text = app.conversationPrompt ?? '';
  p.chatPromptController.text = app.chatPrompt ?? '';
  p.sourceCodeUrlController.text = app.sourceCodeUrl ?? '';
  p.makeAppPublic = !app.private;
  p.appCategory = app.category;
  p.isPaid = app.isPaid;
  p.selectePaymentPlan = app.paymentPlan;
  p.selectedCapabilities = app.capabilities.map((id) => AppCapability(title: id, id: id)).toList();
  p.thumbnailIds = List.of(app.thumbnailIds);
}

void main() {
  group('AddAppProvider.hasDataChanged', () {
    late App app;
    late AddAppProvider provider;

    setUp(() {
      app = _buildApp();
      provider = AddAppProvider();
      _seedMatching(provider, app);
    });

    test('no changes on initial load', () {
      expect(provider.hasDataChanged(app, app.category), isFalse);
    });

    test('free app with an empty price field is not dirty', () {
      // Regression: empty price field on a free app must not read as a change.
      provider.priceController.text = '';
      expect(provider.hasDataChanged(app, app.category), isFalse);
    });

    test('editing the name marks dirty, reverting clears it', () {
      provider.appNameController.text = 'My Template v2';
      expect(provider.hasDataChanged(app, app.category), isTrue);
      provider.appNameController.text = app.name;
      expect(provider.hasDataChanged(app, app.category), isFalse);
    });

    test('editing the description marks dirty', () {
      provider.appDescriptionController.text = 'changed';
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('toggling visibility marks dirty', () {
      provider.makeAppPublic = !provider.makeAppPublic;
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('changing the category marks dirty', () {
      provider.appCategory = 'a-different-category';
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('adding a capability marks dirty', () {
      provider.selectedCapabilities = [...provider.selectedCapabilities, AppCapability(title: 'chat', id: 'chat')];
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('editing the conversation prompt marks dirty', () {
      provider.conversationPromptController.text = 'a new prompt';
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('switching to paid marks dirty', () {
      provider.isPaid = true;
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('picking a new logo marks dirty', () {
      provider.imageFile = File('new_logo.png');
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });
  });

  group('AddAppProvider.hasDataChanged — external integration', () {
    late App app;
    late AddAppProvider provider;

    App buildExtApp() => App.fromJson({
          'id': 'ext_app',
          'name': 'Hooky',
          'author': 'Jane',
          'description': 'integration app',
          'image': 'https://img/logo.png',
          'category': 'productivity-and-organization',
          'capabilities': ['external_integration'],
          'private': true,
          'is_paid': false,
          'price': 0.0,
          'thumbnails': <String>[],
          'external_integration': {
            'triggers_on': 'memory_creation',
            'webhook_url': 'https://hook',
            'auth_steps': [
              {'url': 'https://auth', 'name': 'Setup'},
            ],
            'actions': [
              {'action': 'create_conversation'},
            ],
          },
        });

    setUp(() {
      app = buildExtApp();
      provider = AddAppProvider();
      _seedMatching(provider, app);
      final ext = app.externalIntegration!;
      provider.triggerEvent = ext.triggersOn;
      provider.webhookUrlController.text = ext.webhookUrl ?? '';
      provider.setupCompletedController.text = ext.setupCompletedUrl ?? '';
      provider.instructionsController.text = ext.setupInstructionsFilePath ?? '';
      provider.appHomeUrlController.text = ext.appHomeUrl ?? '';
      provider.chatToolsManifestUrlController.text = ext.chatToolsManifestUrl ?? '';
      provider.authUrlController.text = ext.authSteps.isNotEmpty ? ext.authSteps.first.url : '';
      provider.actions = (ext.actions ?? []).map((a) => {'action': a.action}).toList();
    });

    test('no changes on initial load', () {
      expect(provider.hasDataChanged(app, app.category), isFalse);
    });

    test('editing the auth URL marks dirty', () {
      provider.authUrlController.text = 'https://auth/changed';
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });

    test('changing actions marks dirty', () {
      provider.actions = [
        {'action': 'read_conversations'},
      ];
      expect(provider.hasDataChanged(app, app.category), isTrue);
    });
  });
}
