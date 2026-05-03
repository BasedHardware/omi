import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/apps/apps_storage.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_detail_screen.dart';
import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/widgets/generative_ui/widgets/rich_list_widget.dart';

ApiClient _client(MockClient mock) => ApiClient(
  httpClient: mock,
  getIdToken: ({bool forceRefresh = false}) async => 'tok',
  signOut: () async {},
  baseUrl: 'https://example.test/',
);

Map<String, dynamic> _conversationJson({
  required String id,
  String overview = 'Plain overview text.',
  List<Map<String, dynamic>>? appsResults,
}) {
  return {
    'id': id,
    'created_at': '2026-04-30T10:00:00Z',
    'transcript_segments': const <Map<String, dynamic>>[
      {'speaker': 'SPEAKER_0', 'text': 'Hi', 'is_user': true},
    ],
    'structured': {'title': 'Sample meeting', 'overview': overview, 'action_items': const <Map<String, dynamic>>[]},
    if (appsResults != null) 'apps_results': appsResults,
  };
}

Widget _harness({required AppsProvider apps, required ConversationsProvider convs, required ConversationItem item}) {
  return MaterialApp(
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<AppsProvider>.value(value: apps),
        ChangeNotifierProvider<ConversationsProvider>.value(value: convs),
      ],
      child: ConversationDetailScreen(item: item),
    ),
  );
}

void main() {
  late Directory tempDir;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    tempDir = await Directory.systemTemp.createTemp('detail_apps_results_test');
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

  testWidgets('renders AppResultMarkdown with rich-list when apps_results present', (tester) async {
    final convJson = _conversationJson(
      id: 'c1',
      overview: 'Old overview',
      appsResults: [
        {'app_id': 'app-1', 'content': '<rich-list><item title="Apple"/></rich-list>'},
      ],
    );
    final mock = MockClient((req) async {
      if (req.url.path == '/v1/conversations') {
        return http.Response(jsonEncode([convJson]), 200);
      }
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode({'groups': []}), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode([]), 200);
      }
      return http.Response('not found', 404);
    });
    final apps = AppsProvider(client: _client(mock));
    final convs = ConversationsProvider(client: _client(mock));
    await apps.load();
    await convs.load();
    final item = convs.byId('c1')!;

    await tester.pumpWidget(_harness(apps: apps, convs: convs, item: item));
    await tester.pump();

    expect(find.text('OVERVIEW'), findsOneWidget);
    expect(find.byType(RichListWidget), findsOneWidget);
    expect(find.text('Apple'), findsOneWidget);
  });

  testWidgets('renders fallback overview when apps_results empty', (tester) async {
    final convJson = _conversationJson(id: 'c2', overview: 'Plain overview text.');
    final mock = MockClient((req) async {
      if (req.url.path == '/v1/conversations') {
        return http.Response(jsonEncode([convJson]), 200);
      }
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode({'groups': []}), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode([]), 200);
      }
      return http.Response('not found', 404);
    });
    final apps = AppsProvider(client: _client(mock));
    final convs = ConversationsProvider(client: _client(mock));
    await apps.load();
    await convs.load();
    final item = convs.byId('c2')!;

    await tester.pumpWidget(_harness(apps: apps, convs: convs, item: item));
    await tester.pump();
    expect(find.text('Plain overview text.'), findsOneWidget);
    expect(find.byType(RichListWidget), findsNothing);
  });

  testWidgets('reprocess success → new content rendered', (tester) async {
    final initial = _conversationJson(
      id: 'c3',
      overview: 'Old overview',
      appsResults: [
        {'app_id': 'app-1', 'content': '<rich-list><item title="Old"/></rich-list>'},
      ],
    );
    final updated = _conversationJson(
      id: 'c3',
      overview: 'Old overview',
      appsResults: [
        {'app_id': 'app-2', 'content': '<rich-list><item title="Fresh"/></rich-list>'},
      ],
    );

    final mock = MockClient((req) async {
      if (req.url.path == '/v1/conversations') {
        return http.Response(jsonEncode([initial]), 200);
      }
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode({'groups': []}), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode([]), 200);
      }
      if (req.url.path.contains('/reprocess')) {
        return http.Response(jsonEncode(updated), 200);
      }
      return http.Response('not found', 404);
    });
    final apps = AppsProvider(client: _client(mock));
    final convs = ConversationsProvider(client: _client(mock));
    await apps.load();
    await convs.load();
    final item = convs.byId('c3')!;

    await tester.pumpWidget(_harness(apps: apps, convs: convs, item: item));
    await tester.pump();
    expect(find.text('Old'), findsOneWidget);

    // Trigger reprocess directly through the provider (the picker sheet
    // ultimately calls this same method).
    final ok = await convs.reprocessWithApp('c3', 'app-2');
    expect(ok, isTrue);
    await tester.pump();
    expect(find.text('Fresh'), findsOneWidget);
    expect(find.text('Old'), findsNothing);
  });
}
