import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail_config.dart';

Map<String, dynamic> _appJson(Map<String, dynamic> externalIntegration, {String name = 'Test App'}) {
  return {
    'id': 'app-1',
    'uid': 'user-1',
    'name': name,
    'author': 'Author',
    'description': 'Desc',
    'image': 'https://example.com/icon.png',
    'capabilities': ['external_integration'],
    'status': 'approved',
    'approved': true,
    'rating_count': 0,
    'enabled': true,
    'deleted': false,
    'is_paid': false,
    'category': 'productivity-and-organization',
    'external_integration': externalIntegration,
  };
}

Map<String, dynamic> _integrationJson({
  String appHomeUrl = 'https://example.com/home',
  String setupCompletedUrl = 'https://example.com/setup-done',
  String webhookUrl = 'https://example.com/webhook',
  List<Map<String, String>> authSteps = const [],
}) {
  return {
    'triggers_on': 'memory_creation',
    'webhook_url': webhookUrl,
    'setup_completed_url': setupCompletedUrl,
    'app_home_url': appHomeUrl,
    'auth_steps': authSteps,
  };
}

void main() {
  group('hasExternalIntegrationChanged', () {
    test('returns false for identical integration configs', () {
      final integration = _integrationJson(
        authSteps: [
          {'name': 'Setup', 'url': 'https://example.com/auth'},
        ],
      );
      final current = ExternalIntegration.fromJson(integration);
      final updated = ExternalIntegration.fromJson(integration);
      expect(hasExternalIntegrationChanged(current, updated), isFalse);
    });

    test('returns true when auth step URL changes', () {
      final current = ExternalIntegration.fromJson(
        _integrationJson(authSteps: [
          {'name': 'Setup', 'url': 'https://example.com/old-auth'},
        ]),
      );
      final updated = ExternalIntegration.fromJson(
        _integrationJson(authSteps: [
          {'name': 'Setup', 'url': 'https://example.com/new-auth'},
        ]),
      );
      expect(hasExternalIntegrationChanged(current, updated), isTrue);
    });

    test('returns true when setup completed URL changes', () {
      final current = ExternalIntegration.fromJson(_integrationJson(setupCompletedUrl: 'https://example.com/old-setup'));
      final updated = ExternalIntegration.fromJson(_integrationJson(setupCompletedUrl: 'https://example.com/new-setup'));
      expect(hasExternalIntegrationChanged(current, updated), isTrue);
    });

    test('returns true when webhook URL changes', () {
      final current = ExternalIntegration.fromJson(_integrationJson(webhookUrl: 'https://example.com/old-webhook'));
      final updated = ExternalIntegration.fromJson(_integrationJson(webhookUrl: 'https://example.com/new-webhook'));
      expect(hasExternalIntegrationChanged(current, updated), isTrue);
    });

    test('returns true when one side has no integration', () {
      expect(hasExternalIntegrationChanged(null, ExternalIntegration.fromJson(_integrationJson())), isTrue);
      expect(hasExternalIntegrationChanged(ExternalIntegration.fromJson(_integrationJson()), null), isTrue);
    });
  });

  group('hasAppDetailConfigChanged', () {
    test('returns false when only unrelated app fields change', () {
      final integration = _integrationJson();
      final current = App.fromJson(_appJson(integration));
      final updatedJson = _appJson(integration);
      updatedJson['rating_avg'] = 4.5;
      final updated = App.fromJson(updatedJson);
      expect(hasAppDetailConfigChanged(current, updated), isFalse);
    });

    test('returns true when name changes', () {
      final integration = _integrationJson();
      final current = App.fromJson(_appJson(integration));
      final updated = App.fromJson(_appJson(integration, name: 'Renamed App'));
      expect(hasAppDetailConfigChanged(current, updated), isTrue);
    });

    test('returns true when auth step URL changes without name or home URL changes', () {
      final current = App.fromJson(_appJson(_integrationJson(authSteps: [
        {'name': 'Setup', 'url': 'https://example.com/old-auth'},
      ])));
      final updated = App.fromJson(_appJson(_integrationJson(authSteps: [
        {'name': 'Setup', 'url': 'https://example.com/new-auth'},
      ])));
      expect(hasAppDetailConfigChanged(current, updated), isTrue);
    });

    test('returns true when setup completed URL changes without name or home URL changes', () {
      final current = App.fromJson(_appJson(_integrationJson(setupCompletedUrl: 'https://example.com/old-setup')));
      final updated = App.fromJson(_appJson(_integrationJson(setupCompletedUrl: 'https://example.com/new-setup')));
      expect(hasAppDetailConfigChanged(current, updated), isTrue);
    });
  });
}
