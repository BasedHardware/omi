import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';

void main() {
  group('TaskIntegrationProvider.ensureLoaded', () {
    test('tries again after a load that did not reach the server', () async {
      var calls = 0;
      final provider = TaskIntegrationProvider(getTaskIntegrationsFn: () async {
        calls++;
        if (calls == 1) return null;
        return TaskIntegrationsResponse(integrations: {
          'google_tasks': {'connected': true, 'access_token': 't'}
        }, defaultApp: 'google_tasks');
      });
      addTearDown(provider.dispose);

      await provider.ensureLoaded();
      expect(provider.hasLoaded, isTrue);
      expect(provider.isAppConnected(TaskIntegrationApp.googleTasks), isFalse);

      // The failed first answer is not trusted: the next call loads again and sees the app.
      await provider.ensureLoaded();
      expect(calls, 2);
      expect(provider.isAppConnected(TaskIntegrationApp.googleTasks), isTrue);
      expect(provider.selectedApp, TaskIntegrationApp.googleTasks);

      // A good answer is kept.
      await provider.ensureLoaded();
      expect(calls, 2);
    });

    test('a load while one is in flight joins it instead of fetching twice', () async {
      var calls = 0;
      final provider = TaskIntegrationProvider(getTaskIntegrationsFn: () async {
        calls++;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return TaskIntegrationsResponse(integrations: const {});
      });
      addTearDown(provider.dispose);

      await Future.wait([provider.loadFromBackend(), provider.ensureLoaded(), provider.loadFromBackend()]);
      expect(calls, 1);
      expect(provider.isLoading, isFalse);
      expect(provider.hasLoaded, isTrue);
    });
  });

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
