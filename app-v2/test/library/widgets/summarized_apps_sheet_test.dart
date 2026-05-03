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
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/library/widgets/summarized_apps_sheet.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';

ApiClient _clientWith(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

Map<String, dynamic> _conv({required String id, List<String> suggested = const [], String? currentAppId}) {
  return {
    'id': id,
    'created_at': '2026-04-30T10:00:00Z',
    'structured': {'title': 'Meeting', 'overview': ''},
    'transcript_segments': const <Map<String, dynamic>>[],
    if (currentAppId != null)
      'apps_results': [
        {'app_id': currentAppId, 'content': 'x'},
      ],
    if (suggested.isNotEmpty) 'suggested_summarization_apps': suggested,
  };
}

Widget _harness({required AppsProvider apps, required ConversationsProvider convs, required Widget child}) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<AppsProvider>.value(value: apps),
        ChangeNotifierProvider<ConversationsProvider>.value(value: convs),
      ],
      child: Scaffold(body: child),
    ),
  );
}

MockClient _routingMock({
  required Map<String, dynamic> conv,
  required List<Map<String, dynamic>> catalog,
  required List<String> enabled,
  Map<String, dynamic>? reprocessResponse,
  void Function(String appId)? onReprocess,
}) {
  return MockClient((req) async {
    final path = req.url.path;
    if (path == '/v2/apps') {
      return http.Response(jsonEncode({'groups': catalog}), 200);
    }
    if (path == '/v1/apps/enabled') {
      return http.Response(jsonEncode(enabled), 200);
    }
    if (path == '/v1/conversations') {
      return http.Response(jsonEncode([conv]), 200);
    }
    if (path.contains('/reprocess')) {
      final id = req.url.queryParameters['app_id'] ?? '';
      onReprocess?.call(id);
      return http.Response(jsonEncode(reprocessResponse ?? conv), 200);
    }
    return http.Response('not found', 404);
  });
}

Map<String, dynamic> _appJson({required String id, required String name}) => {
  'id': id,
  'name': name,
  'description': '',
  'image': '',
  'enabled': true,
  'installs': 0,
  'capabilities': const ['memories'],
};

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('summ_apps_sheet_test');
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
    if (await tempDir.exists()) await tempDir.delete(recursive: true);
  });

  testWidgets('renders list of installed apps and highlights current', (tester) async {
    final conv = _conv(id: 'c1', currentAppId: 'a1');
    final mock = _routingMock(
      conv: conv,
      catalog: [
        {
          'capability': {'id': 'memories', 'title': 'Summary'},
          'data': [_appJson(id: 'a1', name: 'Alpha'), _appJson(id: 'a2', name: 'Beta')],
        },
      ],
      enabled: ['a1', 'a2'],
    );
    final apps = AppsProvider(client: _clientWith(mock));
    final convs = ConversationsProvider(client: _clientWith(mock));
    await apps.load();
    await convs.load();

    await tester.pumpWidget(
      _harness(
        apps: apps,
        convs: convs,
        child: SummarizedAppsBottomSheet(conversationId: 'c1', currentAppId: 'a1'),
      ),
    );
    await tester.pump();

    expect(find.text('Alpha'), findsOneWidget);
    expect(find.text('Beta'), findsOneWidget);
    expect(find.text('Currently using'), findsOneWidget);
  });

  testWidgets('shows Suggested badge for apps in suggestedSummarizationApps', (tester) async {
    final conv = _conv(id: 'c1', currentAppId: 'a1', suggested: ['a2']);
    final mock = _routingMock(
      conv: conv,
      catalog: [
        {
          'capability': {'id': 'memories', 'title': 'Summary'},
          'data': [_appJson(id: 'a1', name: 'Alpha'), _appJson(id: 'a2', name: 'Beta')],
        },
      ],
      enabled: ['a1', 'a2'],
    );
    final apps = AppsProvider(client: _clientWith(mock));
    final convs = ConversationsProvider(client: _clientWith(mock));
    await apps.load();
    await convs.load();

    await tester.pumpWidget(
      _harness(
        apps: apps,
        convs: convs,
        child: SummarizedAppsBottomSheet(conversationId: 'c1', currentAppId: 'a1'),
      ),
    );
    await tester.pump();

    expect(find.text('Suggested for this conversation'), findsOneWidget);
  });

  testWidgets('tapping an app calls reprocessWithApp with the right id', (tester) async {
    final conv = _conv(id: 'c1', currentAppId: 'a1');
    String? lastReprocessAppId;
    final mock = _routingMock(
      conv: conv,
      catalog: [
        {
          'capability': {'id': 'memories', 'title': 'Summary'},
          'data': [_appJson(id: 'a1', name: 'Alpha'), _appJson(id: 'a2', name: 'Beta')],
        },
      ],
      enabled: ['a1', 'a2'],
      onReprocess: (id) => lastReprocessAppId = id,
    );
    final apps = AppsProvider(client: _clientWith(mock));
    final convs = ConversationsProvider(client: _clientWith(mock));
    await apps.load();
    await convs.load();

    // Render the sheet body directly (not via showModalBottomSheet) — the
    // modal overlay creates a separate provider tree that the test harness
    // doesn't reach into. The sheet's behavior is what we want to assert.
    await tester.pumpWidget(
      _harness(
        apps: apps,
        convs: convs,
        child: SummarizedAppsBottomSheet(conversationId: 'c1', currentAppId: 'a1'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Beta'));
    await tester.pumpAndSettle();
    expect(lastReprocessAppId, 'a2');
  });
}
