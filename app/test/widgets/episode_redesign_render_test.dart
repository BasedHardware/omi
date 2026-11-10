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

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/home_fixture_env.dart';
import '../helpers/sfpro_font_fixtures.dart';
import 'episode_redesign/fixtures.dart';
import '../helpers/episode_tasks_fixture.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/action_items_provider.dart';

const _output = String.fromEnvironment('EPISODE_REDESIGN_RENDER_OUTPUT');
final _boundary = GlobalKey();
int _ordinal = 0;

Future<void> _fonts() async {
  for (final entry in jsonDecode(await rootBundle.loadString('FontManifest.json')) as List) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  final loader = FontLoader('SF Pro Display');
  for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
    loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
  }
  await loader.load();
  final emoji = File('/System/Library/Fonts/Apple Color Emoji.ttc');
  if (emoji.existsSync()) {
    await (FontLoader('Apple Color Emoji')..addFont(Future.value(ByteData.sublistView(await emoji.readAsBytes()))))
        .load();
  }
}

Future<void> _capture(WidgetTester tester, String slug) async {
  _ordinal++;
  expect(tester.takeException(), isNull);
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    final file = '${_ordinal.toString().padLeft(3, '0')}-mobile-ios-$slug.png';
    await File('$_output/$file').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
}

Future<void> _pump(WidgetTester tester, Episode episode,
    {required bool before,
    Brightness brightness = Brightness.dark,
    Widget? home,
    Episode? detail,
    List<ServerConversation>? cached,
    Future<ApiResult<Episode>> Function(String)? loadDetail}) async {
  final history = ConversationProvider(isSignedIn: () => false)..conversations = [...cached ?? episode.members];
  final episodes = EpisodeProvider()
    ..debugSetLive(null)
    ..debugSetHomeEpisodes([episode]);
  final connectivity = ConnectivityProvider();
  final tasks = episodeTasks();
  addTearDown(tasks.dispose);
  addTearDown(history.dispose);
  addTearDown(episodes.dispose);
  addTearDown(connectivity.dispose);
  OmiColors.active = OmiColors.forBrightness(brightness);
  final baseTheme = buildOmiTheme(brightness: brightness);
  final theme = baseTheme.copyWith(
    textTheme: baseTheme.textTheme.apply(fontFamily: 'SF Pro Display', fontFamilyFallback: const ['Apple Color Emoji']),
    primaryTextTheme:
        baseTheme.primaryTextTheme.apply(fontFamily: 'SF Pro Display', fontFamilyFallback: const ['Apple Color Emoji']),
    appBarTheme: baseTheme.appBarTheme.copyWith(
      titleTextStyle: baseTheme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display'),
    ),
  );
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<ActionItemsProvider>.value(value: tasks),
      ChangeNotifierProvider<ConversationProvider>.value(value: history),
      ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
      ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
    ],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: theme,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: RepaintBoundary(
        key: _boundary,
        child: home ??
            EpisodePage(
                episode: episode,
                readFlag: (_) async => before,
                loadDetail: loadDetail ?? (_) async => ApiSuccess(detail ?? episode)),
      ),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _bottom(WidgetTester tester) async {
  // A ListView may discover more extent as its children are laid out. Bounded scroll to end.
  final scroll = find.descendant(of: find.byType(ListView).first, matching: find.byType(Scrollable)).first;
  for (var i = 0; i < 20; i++) {
    final position = tester.state<ScrollableState>(scroll).position;
    if (position.pixels >= position.maxScrollExtent) break;
    position.jumpTo(position.maxScrollExtent);
    await tester.pump();
  }
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(() async {
    Env.init(HomeFixtureEnv());
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await _fonts();
  });
  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
  });
  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    OmiColors.active = OmiPalette.dark;
  });

  for (final state in ['typical-day', 'many-noisy', 'few-members', 'long-summary']) {
    for (final before in [true, false]) {
      testWidgets('$state ${before ? 'before' : 'after'} review frames', (tester) async {
        tester.view.physicalSize = const Size(393, 852);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final episode = fixture(state);
        final phase = before ? 'before' : 'after';
        await _pump(tester, episode, before: before);
        await _capture(tester, '$state-$phase-top');
        await _bottom(tester);
        await _capture(tester, '$state-$phase-rows');
        if (!before) {
          for (final member in episode.members.where((m) => m.homeStep == 'noise')) {
            expect(find.byKey(ValueKey('compact_${member.id}')), findsNothing);
          }
          if (state == 'many-noisy') {
            expect(find.text('8 short clips hidden'), findsOneWidget);
            await tester.tap(find.byKey(const Key('noise_toggle')));
            await tester.pumpAndSettle();
            await _bottom(tester);
            await _capture(tester, 'many-noisy-after-expanded');
            expect(find.byKey(const ValueKey('compact_noise-7')), findsOneWidget);
          }
          if (state == 'long-summary') {
            expect(find.byKey(const Key('full_summary_toggle')), findsNothing);
            expect(find.text('Summary'), findsNothing);
            await tester.ensureVisible(find.text('Make the invitation feel welcoming'));
            await _capture(tester, 'long-summary-after-expanded');
            await _bottom(tester);
            expect(find.text('An indoor plan if it rains'), findsOneWidget);
            await _capture(tester, 'long-summary-after-ending');
          }
        }
        await tester.pumpWidget(const SizedBox.shrink());
        debugDefaultTargetPlatformOverride = null;
      });
    }
  }

  testWidgets('follow-up plus creates a linked task and becomes a check', (tester) async {
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await _pump(tester, fixture('few-members'), before: false);
    final add = find.byKey(const ValueKey('episode_follow_up_add_Check the seed trays before Saturday.'));
    await tester.ensureVisible(add);
    await _capture(tester, 'follow-up-plus-ready');
    await tester.tap(add);
    await tester.pumpAndSettle();
    expect(find.byTooltip('Added to Tasks'), findsOneWidget);
    await _capture(tester, 'follow-up-plus-saved');
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('full detail restores omitted noise; payload metadata survives an older Home cache', (tester) async {
    final detail = fixture('many-noisy');
    final home = detail.copyWith(members: detail.members.where((m) => m.homeStep != 'noise').toList());
    final cached = [
      for (final m in detail.members)
        ServerConversation(id: m.id, createdAt: m.createdAt, structured: Structured(m.structured.title, ''))
    ];
    await _pump(tester, home, before: false, detail: detail, cached: cached);
    await _bottom(tester);
    expect(find.text('8 short clips hidden'), findsOneWidget);
    expect(find.text('A smaller group, more time for hands-on practice.'), findsOneWidget);
    expect(find.byKey(const ValueKey('compact_noise-7')), findsNothing);
    await tester.tap(find.byKey(const Key('noise_toggle')));
    await tester.pumpAndSettle();
    await _bottom(tester);
    expect(find.byKey(const ValueKey('compact_noise-7')), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('full detail keeps every composed moment omitted from the Home projection', (tester) async {
    final detail = fixture('long-summary');
    final home = Episode(
        id: detail.id,
        live: false,
        startedAt: detail.startedAt,
        lastActivityAt: detail.lastActivityAt,
        title: detail.title,
        lede: detail.lede,
        moments: detail.moments.take(2).toList(),
        members: detail.members,
        conversationIds: detail.conversationIds);
    await _pump(tester, home, before: false, detail: detail);
    expect(find.text('Make the invitation feel welcoming'), findsOneWidget);
    expect(find.text('An indoor plan if it rains'), findsOneWidget);
    expect(find.byKey(const Key('full_summary_toggle')), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('processing stand-in resolves to full detail when composed notes arrive', (tester) async {
    final detail = fixture('many-noisy');
    final opening = Episode(
        id: '',
        live: false,
        startedAt: detail.startedAt,
        lastActivityAt: detail.lastActivityAt,
        members: [detail.members.first],
        conversationIds: [detail.members.first.id]);
    final ids = <String>[];
    await _pump(tester, opening, before: false, loadDetail: (id) async {
      ids.add(id);
      return ApiSuccess(detail);
    });
    expect(ids, isEmpty);
    final provider = Provider.of<EpisodeProvider>(tester.element(find.byType(EpisodePage)), listen: false);
    provider
        .debugSetHomeEpisodes([detail.copyWith(members: detail.members.where((m) => m.homeStep != 'noise').toList())]);
    await tester.pumpAndSettle();
    await _bottom(tester);
    expect(ids, [detail.id]);
    expect(find.text('8 short clips hidden'), findsOneWidget);
    provider.notifyListeners();
    await tester.pump();
    expect(ids, [detail.id], reason: 'Unchanged notes never re-read detail.');
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('old server retains opening snapshot; kill switch skips new detail request', (tester) async {
    var calls = 0;
    Future<ApiResult<Episode>> unavailable(String id) async {
      calls++;
      return const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));
    }

    await _pump(tester, fixture('few-members'), before: false, loadDetail: unavailable);
    expect(find.byKey(const Key('episode_summary')), findsOneWidget);
    expect(calls, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    await _pump(tester, fixture('few-members'), before: true, loadDetail: unavailable);
    expect(find.byKey(const Key('episode_summary')), findsNothing);
    expect(calls, 1);
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('Home episode row has no member count', (tester) async {
    tester.view.physicalSize = const Size(393, 220);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final episode = fixture('many-noisy');
    await _pump(tester, episode,
        before: true,
        home: Scaffold(
          appBar: AppBar(title: const Text('Home')),
          body: Column(
            children: [
              ConversationListItem(
                conversation: ServerConversation(
                    id: 'episode:${episode.id}',
                    createdAt: episode.startedAt,
                    startedAt: episode.startedAt,
                    finishedAt: episode.lastActivityAt,
                    structured: Structured(episode.title, '', emoji: '💬')),
                date: episode.startedAt,
                conversationIdx: -1,
                homeEpisode: episode,
              )
            ],
          ),
        ));
    expect(find.textContaining('conversations'), findsNothing);
    expect(find.text('10'), findsNothing);
    expect(find.textContaining('parts'), findsNothing);
    await _capture(tester, 'home-episode-no-count');
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('episode detail fits light mode at narrow width and larger type', (tester) async {
    tester.view.physicalSize = const Size(320, 852);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await _pump(tester, fixture('many-noisy'), before: false, brightness: Brightness.light);
    await _capture(tester, 'narrow-light-after-top');
    await _bottom(tester);
    final timestamp =
        find.descendant(of: find.byKey(const ValueKey('compact_supplies')), matching: find.byType(Text)).first;
    final paragraph = tester.renderObject<RenderParagraph>(timestamp);
    final text = tester.widget<Text>(timestamp).data!;
    final lines = paragraph
        .getBoxesForSelection(TextSelection(baseOffset: 0, extentOffset: text.length))
        .map((box) => box.top)
        .toSet();
    expect(lines, hasLength(1), reason: 'The complete time stays on one line at larger text sizes.');
    await _capture(tester, 'narrow-light-after-rows');
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });
}
