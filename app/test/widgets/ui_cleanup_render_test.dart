import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/held_audio/held_audio_views.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Home after the UI cleanup: only Questions for you above the list, and recordings waiting for a
/// plan back as locked rows that open the plans. CI runs it as a layout check.
const _output = String.fromEnvironment('UI_CLEANUP_RENDER_OUTPUT');

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String get apiBaseUrl => '';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
}

final _start = DateTime(2026, 10, 27, 21, 59).millisecondsSinceEpoch ~/ 1000;
final _recordings = [
  for (final (i, s) in [9, 8, 10].indexed) HeldAudioRecording(id: 'r$i', startedAt: _start + i * 3600, seconds: s * 60),
];

/// Search with one short clip among the discarded rows the filter asks for.
class _ClipSearch extends GlobalSearchSource {
  @override
  Future<ApiResult<SearchOverview>> overview() async =>
      const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

  @override
  Future<ConversationSearchResult> conversations(String query,
      {String? speakerId, DateTime? startDate, DateTime? endDate, bool includeNoise = false}) async {
    final started = DateTime(2026, 10, 30, 14, 5);
    return ConversationSearchResult(items: [
      if (includeNoise)
        ServerConversation.fromJson({
          'id': 'clip',
          'created_at': started.toUtc().toIso8601String(),
          'started_at': started.toUtc().toIso8601String(),
          'finished_at': started.add(const Duration(seconds: 20)).toUtc().toIso8601String(),
          'structured': {'title': 'TV in the background', 'overview': '', 'emoji': '', 'category': 'other'},
          'status': 'completed',
          'discarded': true,
          'content_kind': 'media',
          'transcript_segments': [],
        }),
    ], currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);
  }

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];
  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async => const ApiSuccess(<DailySummary>[]);
  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async =>
      const ApiSuccess(<ActionItemWithMetadata>[]);
  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async => const ApiSuccess(<MemorySearchHit>[]);
}

Future<void> _snap(WidgetTester tester, GlobalKey boundary, String name) async {
  expect(tester.takeException(), isNull);
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });
  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<GlobalKey> pump(WidgetTester tester, Widget body, {double height = 852, ReviewProvider? review}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = Size(393, height);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final boundary = GlobalKey();
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: MultiProvider(
        providers: [ChangeNotifierProvider<ReviewProvider?>.value(value: review)],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.light),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(backgroundColor: OmiColors.surface0, body: SafeArea(child: body)),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    return boundary;
  }

  testWidgets('Home: Questions for you, then locked recording rows', (tester) async {
    late ReviewProvider review;
    await tester.runAsync(() async {
      review = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [
          ReviewItem(itemId: 'task:c1', kind: ReviewItemKind.task, task: TaskItem(candidateId: 'c1', description: 'x')),
          ReviewItem(itemId: 'task:c2', kind: ReviewItemKind.task, task: TaskItem(candidateId: 'c2', description: 'y')),
        ], remainingToday: 2)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])),
      );
      await review.load();
    });
    final b = await pump(
        tester,
        ListView(children: [
          const ReviewEntryCard(),
          for (final (i, r) in _recordings.indexed)
            HeldRecordingLockedRow(recording: r, more: i == _recordings.length - 1 ? 59 : 0, onPressed: () {}),
        ]),
        review: review);
    expect(find.byType(HeldRecordingLockedRow), findsNWidgets(3));
    await _snap(tester, b, '001-mobile-ios-home-locked-rows');
    review.dispose();
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('short clips are found in search, behind their own filter', (tester) async {
    final b = await pump(
        tester,
        ChangeNotifierProvider(
          create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[]),
          child: GlobalSearchPage(initialQuery: 'tv', source: _ClipSearch()),
        ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('global_search_noise_filter')));
    await tester.pumpAndSettle();
    expect(find.text('TV in the background'), findsOneWidget);
    await _snap(tester, b, '003-mobile-ios-search-short-clips-filter');
    debugDefaultTargetPlatformOverride = null;
  });
}
