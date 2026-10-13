import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('one malformed status leaves a terminal retry row without hiding successful services', () async {
    var fail = true;
    final provider = IntegrationProvider(
        fetchStatus: (key) async {
          if (key == 'gmail' && fail) throw const FormatException('malformed response');
          return IntegrationResponse(appKey: key, connected: true);
        },
        persistPref: (_, __) async {});
    addTearDown(provider.dispose);
    await provider.loadFromBackend();
    expect(provider.hasLoaded, isTrue);
    expect(provider.isLoading, isFalse);
    expect(provider.hasStatusError(IntegrationApp.gmail), isTrue);
    expect(provider.isAppConnected(IntegrationApp.googleCalendar), isTrue);
    fail = false;
    await provider.ensureLoaded();
    expect(provider.hasStatusError(IntegrationApp.gmail), isFalse);
    expect(provider.isAppConnected(IntegrationApp.gmail), isTrue);
  });

  testWidgets('a nonresponding integration has a bounded status read and ignores its late reply', (tester) async {
    final pending = Completer<IntegrationResponse?>();
    final provider = IntegrationProvider(
        statusTimeout: const Duration(seconds: 1),
        fetchStatus: (key) =>
            key == 'gmail' ? pending.future : Future.value(IntegrationResponse(appKey: key, connected: true)),
        persistPref: (_, __) async {});
    addTearDown(provider.dispose);
    final load = provider.loadFromBackend();
    await tester.pump(const Duration(seconds: 2));
    await load;
    expect(provider.isLoading, isFalse);
    expect(provider.hasLoaded, isTrue);
    expect(provider.hasStatusError(IntegrationApp.gmail), isTrue);
    pending.complete(IntegrationResponse(appKey: 'gmail', connected: true));
    await tester.pump();
    expect(provider.isAppConnected(IntegrationApp.gmail), isFalse);
  });

  test('post-OAuth refresh owns status even when the earlier pre-auth read finishes later', () async {
    final old = Completer<IntegrationResponse?>();
    var fresh = false;
    final provider = IntegrationProvider(
        fetchStatus: (key) => fresh ? Future.value(IntegrationResponse(appKey: key, connected: true)) : old.future,
        persistPref: (_, __) async {});
    addTearDown(provider.dispose);
    final first = provider.loadFromBackend();
    fresh = true;
    await provider.loadFromBackend(forceRefresh: true);
    old.complete(IntegrationResponse(appKey: 'gmail', connected: false));
    await first;
    expect(provider.isAppConnected(IntegrationApp.gmail), isTrue);
    expect(provider.hasStatusError(IntegrationApp.gmail), isFalse);
  });

  test('task read failures preserve verified grants and recover on retry', () async {
    TaskIntegrationsResponse? response = TaskIntegrationsResponse(integrations: {
      'todoist': {'app_key': 'todoist', 'connected': true}
    }, defaultApp: 'todoist');
    final provider = TaskIntegrationProvider(fetchStatus: () async => response);
    addTearDown(provider.dispose);
    provider.clearUserData();
    await provider.loadFromBackend();
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    response = null;
    await provider.loadFromBackend();
    expect(provider.hasLoadError, isTrue);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    response = TaskIntegrationsResponse(integrations: {'todoist': 'malformed'});
    await provider.loadFromBackend();
    expect(provider.hasLoadError, isTrue);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isTrue);
    response = TaskIntegrationsResponse(integrations: {});
    await provider.loadFromBackend();
    expect(provider.hasLoadError, isFalse);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isFalse);
  });

  testWidgets('task timeout ends loading and late results cannot resurrect a cleared account', (tester) async {
    final pending = Completer<TaskIntegrationsResponse?>();
    final provider =
        TaskIntegrationProvider(fetchStatus: () => pending.future, statusTimeout: const Duration(seconds: 1));
    addTearDown(provider.dispose);
    provider.clearUserData();
    final load = provider.loadFromBackend();
    await tester.pump(const Duration(seconds: 2));
    await load;
    expect(provider.hasLoaded, isTrue);
    expect(provider.isLoading, isFalse);
    expect(provider.hasLoadError, isTrue);
    provider.clearUserData();
    pending.complete(TaskIntegrationsResponse(integrations: {
      'todoist': {'app_key': 'todoist', 'connected': true}
    }));
    await tester.pump();
    expect(provider.hasLoaded, isFalse);
    expect(provider.isAppConnected(TaskIntegrationApp.todoist), isFalse);
  });

  test('task resumed refresh supersedes an older read', () async {
    final old = Completer<TaskIntegrationsResponse?>();
    var fresh = false;
    final provider = TaskIntegrationProvider(
        fetchStatus: () =>
            fresh ? Future.value(TaskIntegrationsResponse(integrations: {}, defaultApp: 'asana')) : old.future);
    addTearDown(provider.dispose);
    final first = provider.loadFromBackend();
    fresh = true;
    await provider.loadFromBackend(forceRefresh: true);
    old.complete(TaskIntegrationsResponse(integrations: {}, defaultApp: 'todoist'));
    await first;
    expect(provider.selectedApp, TaskIntegrationApp.asana);
  });
  testWidgets('default selection deadline preserves the previous choice and ignores late acceptance', (tester) async {
    final pending = Completer<bool>();
    final provider = TaskIntegrationProvider(
        setDefaultTaskIntegrationFn: (_) => pending.future, statusTimeout: const Duration(seconds: 1));
    addTearDown(provider.dispose);
    final previous = provider.selectedApp;
    bool? saved;
    unawaited(provider.setSelectedApp(TaskIntegrationApp.todoist).then((value) => saved = value));
    await tester.pump(const Duration(seconds: 2));
    expect(saved, isFalse);
    expect(provider.selectedApp, previous);
    pending.complete(true);
    await tester.pump();
    expect(provider.selectedApp, previous);
  });

  test('a status read crossing a successful default write cannot restore the old default', () async {
    final pending = Completer<TaskIntegrationsResponse?>();
    final provider =
        TaskIntegrationProvider(fetchStatus: () => pending.future, setDefaultTaskIntegrationFn: (_) async => true);
    addTearDown(provider.dispose);
    final read = provider.loadFromBackend();
    await provider.setSelectedApp(TaskIntegrationApp.todoist);
    pending.complete(TaskIntegrationsResponse(integrations: {}, defaultApp: 'asana'));
    await read;
    expect(provider.selectedApp, TaskIntegrationApp.todoist);
    expect(provider.isLoading, isFalse);
  });
  test('all task services accept the actual token-free server status DTO', () async {
    final keys = ['todoist', 'asana', 'google_tasks', 'clickup'];
    final reply = TaskIntegrationsResponse.fromJson({
      'integrations': {
        for (final key in keys) key: {'app_key': key, 'connected': true},
      },
      'default_app': 'google_tasks'
    });
    final provider = TaskIntegrationProvider(fetchStatus: () async => reply);
    addTearDown(provider.dispose);
    provider.clearUserData();
    await provider.loadFromBackend();
    expect(provider.hasLoadError, isFalse);
    for (final app in [
      TaskIntegrationApp.todoist,
      TaskIntegrationApp.asana,
      TaskIntegrationApp.googleTasks,
      TaskIntegrationApp.clickup
    ]) {
      expect(provider.isAppConnected(app), isTrue, reason: app.key);
    }
  });
}
