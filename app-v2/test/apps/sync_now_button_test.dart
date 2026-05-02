import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/apps/apps_storage.dart';
import 'package:nooto_v2/apps/widgets/sync_now_button.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _api(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

Widget _harness(AppsProvider provider, {String appId = 'nooto-jira'}) {
  return MaterialApp(
    home: ChangeNotifierProvider<AppsProvider>.value(
      value: provider,
      child: Scaffold(body: SyncNowButton(appId: appId)),
    ),
  );
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('sync_now_button_test');
    Hive.init(tempDir.path);
  });

  setUp(() async {
    if (!Hive.isBoxOpen(AppsBoxes.prefs)) {
      await Hive.openBox<Map>(AppsBoxes.prefs);
    }
    await Hive.box<Map>(AppsBoxes.prefs).clear();
  });

  tearDownAll(() async {
    await Hive.deleteFromDisk();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  testWidgets('renders Sync now label and an icon', (tester) async {
    final mock = MockClient((req) async => http.Response('{}', 200));
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));

    expect(find.text('Sync now'), findsOneWidget);
    expect(find.byIcon(Icons.sync_rounded), findsOneWidget);
  });

  testWidgets('tap triggers POST and shows "Synced N items." snackbar on success', (tester) async {
    String? capturedPath;
    final mock = MockClient((req) async {
      if (req.url.path == '/v1/integrations/nooto-jira/sync-now') {
        capturedPath = req.url.path;
        return http.Response(jsonEncode({'synced': 3, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pump(); // start the async work
    await tester.pumpAndSettle();

    expect(capturedPath, '/v1/integrations/nooto-jira/sync-now');
    expect(find.text('Synced 3 items.'), findsOneWidget);
  });

  testWidgets('singular item copy when synced == 1', (tester) async {
    final mock = MockClient((req) async {
      return http.Response(jsonEncode({'synced': 1, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200);
    });
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pumpAndSettle();

    expect(find.text('Synced 1 item.'), findsOneWidget);
  });

  testWidgets('synced == 0 shows "Already up to date."', (tester) async {
    final mock = MockClient((req) async {
      return http.Response(jsonEncode({'synced': 0, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200);
    });
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pumpAndSettle();

    expect(find.text('Already up to date.'), findsOneWidget);
  });

  testWidgets('400 jira_not_installed shows "Install Jira first."', (tester) async {
    final mock = MockClient((req) async {
      return http.Response(jsonEncode({'detail': 'jira_not_installed'}), 400);
    });
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pumpAndSettle();

    expect(find.text('Install Jira first.'), findsOneWidget);
  });

  testWidgets('502 jira_plugin_error shows "Couldn\'t reach Jira. Try again."', (tester) async {
    final mock = MockClient((req) async {
      return http.Response(jsonEncode({'detail': 'jira_plugin_error'}), 502);
    });
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pumpAndSettle();

    expect(find.text("Couldn't reach Jira. Try again."), findsOneWidget);
  });

  testWidgets('network error shows "Connection failed. Try again."', (tester) async {
    final mock = MockClient((req) async => http.Response('boom', 500));
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));
    await tester.tap(find.byType(SyncNowButton));
    await tester.pumpAndSettle();

    expect(find.text('Connection failed. Try again.'), findsOneWidget);
  });

  testWidgets('disabled (onPressed null) and shows spinner while syncing', (tester) async {
    final completer = Completer<http.Response>();
    final mock = MockClient((req) async => completer.future);
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));

    // Tap dispatches the tap event but the async work (provider.syncNow)
    // is still in flight against the unresolved completer.
    await tester.tap(find.byType(SyncNowButton));
    // Pump once so the provider's first notifyListeners (set isSyncing
    // = true) settles into a rebuild.
    await tester.pump();

    final btn = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(btn.onPressed, isNull, reason: 'button should be disabled while syncing');
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byIcon(Icons.sync_rounded), findsNothing);

    completer.complete(
      http.Response(jsonEncode({'synced': 0, 'errors': 0, 'last_synced_at': '2026-05-01T00:00:00Z'}), 200),
    );
    await tester.pumpAndSettle();

    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('button height meets 44pt minimum touch target', (tester) async {
    final mock = MockClient((req) async => http.Response('{}', 200));
    final provider = AppsProvider(client: _api(mock));

    await tester.pumpWidget(_harness(provider));

    final box = tester.getSize(find.byType(FilledButton));
    expect(box.height, greaterThanOrEqualTo(44.0));
  });
}
