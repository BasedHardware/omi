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
import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/library/widgets/app_result_markdown.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/widgets/generative_ui/widgets/rich_list_widget.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';

ApiClient _client(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

ConversationItem _conv({String overview = '', List<Map<String, dynamic>>? appsResults}) {
  return ConversationItem.fromJson({
    'id': 'c1',
    'created_at': '2026-04-30T10:00:00Z',
    'structured': {'title': 'Meeting', 'overview': overview},
    'transcript_segments': const <Map<String, dynamic>>[],
    if (appsResults != null) 'apps_results': appsResults,
  });
}

Widget _harness({required Widget child, required AppsProvider apps}) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: ChangeNotifierProvider<AppsProvider>.value(
      value: apps,
      child: Scaffold(body: child),
    ),
  );
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('app_result_md_test');
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

  AppsProvider appsProviderWithCatalog() {
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(
          jsonEncode({
            'groups': [
              {
                'capability': {'id': 'memories', 'title': 'Summary'},
                'data': [
                  {
                    'id': 'app-1',
                    'name': 'Default Summary',
                    'description': '',
                    'image': '',
                    'enabled': true,
                    'installs': 0,
                    'capabilities': const ['memories'],
                  },
                ],
              },
            ],
          }),
          200,
        );
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode(['app-1']), 200);
      }
      return http.Response('[]', 200);
    });
    return AppsProvider(client: _client(mock));
  }

  testWidgets('renders apps_results[0].content via generative UI', (tester) async {
    final apps = appsProviderWithCatalog();
    await apps.load();
    final item = _conv(
      overview: 'Should not be shown when apps_results exists',
      appsResults: [
        {
          'app_id': 'app-1',
          'content': '''<rich-list>
  <item title="Apple"/>
  <item title="Banana"/>
</rich-list>''',
        },
      ],
    );

    await tester.pumpWidget(
      _harness(
        apps: apps,
        child: AppResultMarkdown(item: item, onPickApp: () {}),
      ),
    );
    await tester.pump();
    expect(find.byType(RichListWidget), findsOneWidget);
    expect(find.text('Apple'), findsOneWidget);
    expect(find.text('Banana'), findsOneWidget);
  });

  testWidgets('falls back to Structured.overview when apps_results empty', (tester) async {
    final apps = appsProviderWithCatalog();
    final item = _conv(overview: 'Plain overview body.');

    await tester.pumpWidget(
      _harness(
        apps: apps,
        child: AppResultMarkdown(item: item, onPickApp: () {}),
      ),
    );
    await tester.pump();
    expect(find.text('Plain overview body.'), findsOneWidget);
    // No app result → no attribution / no rich-list.
    expect(find.byType(RichListWidget), findsNothing);
  });

  testWidgets('hides attribution row when apps_results empty', (tester) async {
    final apps = appsProviderWithCatalog();
    final item = _conv(overview: 'Plain overview body.');

    await tester.pumpWidget(
      _harness(
        apps: apps,
        child: AppResultMarkdown(item: item, onPickApp: () {}),
      ),
    );
    await tester.pump();
    // Attribution row label uses summarizedBy/summaryTemplate text — neither
    // should be rendered in the fallback overview state.
    expect(find.text('Summary template'), findsNothing);
  });

  testWidgets('shows attribution row with app name when apps_results present', (tester) async {
    final apps = appsProviderWithCatalog();
    await apps.load();
    final item = _conv(
      appsResults: [
        {'app_id': 'app-1', 'content': 'Some summary text.'},
      ],
    );

    await tester.pumpWidget(
      _harness(
        apps: apps,
        child: AppResultMarkdown(item: item, onPickApp: () {}),
      ),
    );
    await tester.pump();
    expect(find.text('Summarized by Default Summary'), findsOneWidget);
  });

  testWidgets('renders shimmer/spinner while reprocessing', (tester) async {
    final apps = appsProviderWithCatalog();
    final item = _conv(
      appsResults: [
        {'app_id': 'app-1', 'content': 'Existing content'},
      ],
    );

    await tester.pumpWidget(
      _harness(
        apps: apps,
        child: AppResultMarkdown(item: item, onPickApp: () {}, reprocessing: true),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    // The existing content should not be visible during reprocess.
    expect(find.text('Existing content'), findsNothing);
  });
}
