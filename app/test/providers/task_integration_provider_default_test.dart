import 'dart:async';

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

    test('overlapping default saves land in choice order and only the latest publishes', () async {
      final writes = <String>[];
      final pending = <String, Completer<bool>>{};
      final provider = TaskIntegrationProvider(setDefaultTaskIntegrationFn: (key) {
        writes.add(key);
        return (pending[key] = Completer<bool>()).future;
      });
      addTearDown(provider.dispose);

      final todoist = provider.setSelectedApp(TaskIntegrationApp.todoist);
      await Future<void>.delayed(Duration.zero);
      final asana = provider.setSelectedApp(TaskIntegrationApp.asana);
      await Future<void>.delayed(Duration.zero);
      // The ordering that loses the user's choice: the newer save finishes first.
      if (pending['asana'] != null) pending['asana']!.complete(true);
      pending['todoist']!.complete(true);
      await Future<void>.delayed(Duration.zero);
      pending['asana']?.isCompleted == false ? pending['asana']!.complete(true) : null;

      expect(await todoist, isFalse, reason: 'a superseded save never publishes');
      expect(await asana, isTrue);
      expect(writes, ['todoist', 'asana'], reason: 'the server receives choices in the order they were made');
      expect(provider.selectedApp, TaskIntegrationApp.asana);
    });

    test('a queued choice superseded before it is sent is never written', () async {
      final writes = <String>[];
      final first = Completer<bool>();
      final provider = TaskIntegrationProvider(setDefaultTaskIntegrationFn: (key) {
        writes.add(key);
        return key == TaskIntegrationApp.todoist.key ? first.future : Future.value(true);
      });
      addTearDown(provider.dispose);

      final todoist = provider.setSelectedApp(TaskIntegrationApp.todoist);
      await Future<void>.delayed(Duration.zero); // Todoist's write is in flight
      final asana = provider.setSelectedApp(TaskIntegrationApp.asana);
      final clickup = provider.setSelectedApp(TaskIntegrationApp.clickup);
      first.complete(true);

      expect(await todoist, isFalse);
      expect(await asana, isFalse);
      expect(await clickup, isTrue);
      expect(writes, ['todoist', 'clickup']);
      expect(provider.selectedApp, TaskIntegrationApp.clickup);
    });
  });
}
