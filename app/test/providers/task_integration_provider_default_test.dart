import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';

void main() {
  group('TaskIntegrationProvider.setSelectedApp', () {
    test('keeps the previous selection when the server rejects the default change', () async {
      final provider = TaskIntegrationProvider(
        setDefaultTaskIntegrationFn: (appKey) async {
          expect(appKey, TaskIntegrationApp.todoist.key);
          return false;
        },
      );
      addTearDown(provider.dispose);
      final previous = provider.selectedApp;

      final result = await provider.setSelectedApp(TaskIntegrationApp.todoist);

      expect(result, isFalse);
      expect(provider.selectedApp, previous);
    });

    test('publishes the new selection after the server accepts it', () async {
      final provider = TaskIntegrationProvider(
        setDefaultTaskIntegrationFn: (appKey) async {
          expect(appKey, TaskIntegrationApp.todoist.key);
          return true;
        },
      );
      addTearDown(provider.dispose);

      final result = await provider.setSelectedApp(TaskIntegrationApp.todoist);

      expect(result, isTrue);
      expect(provider.selectedApp, TaskIntegrationApp.todoist);
    });
  });
}
