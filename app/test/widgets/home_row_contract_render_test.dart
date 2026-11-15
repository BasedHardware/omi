import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/ui/ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../helpers/home_fixture_env.dart';
import '../helpers/home_one_processing_fixture.dart';
import '../helpers/home_ready_members_fixture.dart';
import '../helpers/sfpro_font_fixtures.dart';
import '../support/typed_conversation_screen.dart';

const _output = String.fromEnvironment('HOME_ROW_RENDER_OUTPUT');
const _baseline = bool.fromEnvironment('HOME_OVERLAP_BASELINE');

class _LiveCapture extends CaptureProvider {
  _LiveCapture()
      : super(
            externalActions: const NoopCaptureExternalActions(),
            inProgressConversationLoader: () async {},
            localSegmentStore: LocalSegmentStore.disabled());
  @override
  String? get liveCaptureSource => 'omi';
  @override
  bool get pendantCaptureVerified => true;
}

const _phone = Size(393, 852);
const _tall = Size(393, 3200);
const _processingKey = Key('home_processing_row');

// English strings the rows render (lib/l10n/app_en.arb).
const _processing = 'Processing…';
const _transcribing = 'Transcribing…';
const _couldntProcess = "Couldn't process";

Future<void> _fonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final entry in manifest) {
    final loader = FontLoader(entry['family'] as String);
    for (final font in entry['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
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

/// A conversation row. An empty [title] with no [overview] is an empty capture
/// awaiting its transcript; a [provenance] of 'server_minimum' is a stand-in title.
ServerConversation _conv(
  String id,
  DateTime start, {
  String title = '',
  String overview = '',
  Duration length = Duration.zero,
  String emoji = '',
  String? provenance,
  String? homeStep,
  bool isLocked = false,
}) =>
    ServerConversation(
      id: id,
      createdAt: start,
      startedAt: start,
      finishedAt: length == Duration.zero ? null : start.add(length),
      structured: Structured(title, overview, emoji: emoji, titleProvenance: provenance),
      homeStep: homeStep,
      isLocked: isLocked,
    );

ConversationProvider _conversationsFor(List<ServerConversation> items) {
  final byDay = <DateTime, List<ServerConversation>>{};
  for (final c in items) {
    final s = c.startedAt!.toLocal();
    (byDay[DateTime(s.year, s.month, s.day)] ??= []).add(c);
  }
  for (final list in byDay.values) {
    list.sort((a, b) => b.startedAt!.compareTo(a.startedAt!));
  }
  return ConversationProvider(
    isSignedIn: () => true,
    conversationListFetcher: () async => (items: items, ok: true),
    dailySummariesChecker: () async => false,
  )
    ..conversations = items
    ..groupedConversations = byDay;
}

EpisodeProvider _episodes() => EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
      fetchPage: (from, to, {cursor}) async => const ApiSuccess(EpisodePageRead(enabled: true)),
    );

/// Pumps the real Home (ConversationsPage) with [items] on a tall view so every row is
/// built for assertions. Returns the boundary key used by [_capture].
Future<GlobalKey> _pumpHome(WidgetTester tester, List<ServerConversation> items,
    {EpisodeProvider? episodeProvider,
    HomeFeedProvider? feed,
    CaptureProvider? capture,
    bool withNavigation = false,
    List<ServerConversation> detailItems = const [],
    void Function(String)? onDetailFetch,
    List<ServerConversation> processing = const []}) async {
  debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = _tall;
  addTearDown(tester.view.reset);
  OmiColors.active = OmiPalette.light;
  addTearDown(() => OmiColors.active = OmiPalette.light);
  SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
  await SharedPreferencesUtil.init();
  final conversations = _conversationsFor(items)..processingConversations = processing;
  final episodes = episodeProvider ?? _episodes();
  addTearDown(() {
    conversations.dispose();
    episodes.dispose();
  });
  final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(
          PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled));
  await store.refresh();
  addTearDown(store.dispose);
  final boundary = GlobalKey();
  Widget screen = await buildTypedConversationScreen(
    conversations,
    pendingWork: store,
    episodes: episodes,
    feed: feed,
    captureProvider: capture,
    initializePreferences: false,
    theme: buildOmiTheme(brightness: Brightness.light),
  );
  if (withNavigation) {
    final apps = AppProvider();
    final detail = ConversationDetailProvider(fetchConversation: (id) async {
      onDetailFetch?.call(id);
      return [...detailItems, ...items].where((c) => c.id == id).firstOrNull;
    });
    detail.setProviders(apps, conversations);
    addTearDown(apps.dispose);
    addTearDown(detail.dispose);
    screen = MultiProvider(providers: [
      ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
      if (feed != null) ChangeNotifierProvider<HomeFeedProvider>.value(value: feed),
      ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
      ChangeNotifierProvider<AppProvider>.value(value: apps),
      ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
      ChangeNotifierProvider(create: (_) => FolderProvider()),
      ChangeNotifierProvider(create: (_) => IntegrationProvider()),
      ChangeNotifierProvider(create: (_) => UsageProvider()),
      ChangeNotifierProvider(create: (_) => MessageProvider()),
    ], child: screen);
  }
  await tester.pumpWidget(RepaintBoundary(
    key: boundary,
    child: screen,
  ));
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 300));
  }
  expect(tester.takeException(), isNull);
  return boundary;
}

/// Saves the first phone-sized screen (393x852 logical, 3x pixels) of the Home page.
Future<void> _capture(WidgetTester tester, GlobalKey boundary, String name) async {
  tester.view.physicalSize = _phone;
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 300));
  expect(tester.takeException(), isNull);
  if (_output.isNotEmpty) {
    await tester.runAsync(() async {
      final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(_output).create(recursive: true);
      await File('$_output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    });
  }
  debugDefaultTargetPlatformOverride = null;
}

void _expectAbsent(List<String> titles) {
  for (final title in titles) {
    expect(find.text(title), findsNothing, reason: '"$title" must not show on Home');
  }
}

double _top(WidgetTester tester, Finder finder) => tester.getTopLeft(finder).dy;

void main() {
  for (final compact in [false, true]) {
    testWidgets('reported settled-noise and older-local shape compact=$compact', (tester) async {
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      // Establish the fixture account before owner-fenced episode reads. A
      // later mock-account reset must not invalidate the live snapshot mid-frame.
      SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
      await SharedPreferencesUtil.init();
      final fixture = HomeSettledNoiseFixture(DateTime.now());
      final episodes = EpisodeProvider(
          fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: fixture.live)),
          lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
          fetchPage: (from, to, {cursor}) async =>
              ApiSuccess(EpisodePageRead(enabled: true, episodes: [fixture.waiting, fixture.older])));
      await episodes.refreshLive();
      episodes.debugSetHomeEpisodes(compact ? [] : [fixture.waiting, fixture.older]);
      final feed = HomeFeedProvider(
          owner: () => 'synthetic-shape',
          fetch: ({cursor}) async => ApiSuccess(HomeFeedPage(items: [
                for (final member in fixture.members)
                  HomeFeedCard(
                      id: 'conversation:${member.id}',
                      kind: 'conversation',
                      detailId: member.id,
                      startedAt: member.startedAt,
                      finishedAt: member.finishedAt,
                      title: member.structured.title,
                      emoji: '',
                      preview: member.structured.overview,
                      status: 'completed',
                      homeStep: member.homeStep,
                      starred: false,
                      isLocked: false,
                      hasTasks: false,
                      memberCount: 1,
                      sources: const [],
                      summaryAvailable: member.homeStep == 'ready',
                      revision: 'shape')
              ], nextCursor: null, hasMore: false, truncated: false, generation: 'shape')));
      addTearDown(feed.dispose);
      if (compact) await feed.start();
      final capture = _LiveCapture();
      addTearDown(capture.dispose);
      final boundary = await _pumpHome(tester, compact ? [] : fixture.members,
          episodeProvider: episodes, feed: compact ? feed : null, capture: capture, processing: fixture.localPending);
      expect(find.byType(LiveEpisodeRow), findsOneWidget);
      expect(find.text('Listening now'), findsOneWidget);
      if (_baseline) {
        expect(find.byType(ProcessingConversationRow), findsNWidgets(4));
        expect(find.text('Transcribing… · 13 recordings'), findsOneWidget);
        expect(find.text('Writing notes… · 1h 45m'), findsOneWidget);
        expect(find.text('Writing notes… · 22m'), findsOneWidget);
        expect(find.text('Writing notes… · 2m 52s'), findsOneWidget);
      } else {
        expect(find.byType(ProcessingConversationRow), findsOneWidget);
        final pending = tester.widget<ProcessingConversationRow>(find.byType(ProcessingConversationRow));
        expect(pending.count, 3);
        expect(pending.step.name, 'transcribing');
        expect(pending.episode!.members.map((m) => m.id).toSet(), fixture.localPending.map((m) => m.id).toSet());
        expect(find.text('Transcribing… · 3 recordings'), findsOneWidget);
        expect(find.textContaining('Writing notes'), findsNothing);
        expect(_top(tester, find.byType(LiveEpisodeRow)), lessThan(_top(tester, find.byKey(_processingKey))));
        for (final member in fixture.members.take(10)) {
          expect(find.text(member.structured.title), findsOneWidget);
          expect(_top(tester, find.byKey(_processingKey)),
              lessThan(_top(tester, find.byKey(ValueKey(compact ? 'conversation:${member.id}' : member.id)))));
        }
        for (final member in fixture.members.skip(10)) {
          expect(find.byKey(ValueKey(member.id)), findsNothing);
        }
      }
      await _capture(
          tester,
          boundary,
          _baseline
              ? '007-mobile-ios-reported-shape-before'
              : compact
                  ? '008-mobile-ios-reported-shape-after'
                  : 'reported-shape-legacy-after');
      expect(find.text('Listening now'), findsOneWidget, reason: 'capture keeps the real visible live row');
      await tester.pumpWidget(const SizedBox.shrink());
      episodes.invalidateHome();
    }, skip: _baseline && compact);
  }

  testWidgets('compact cards fold pending only and atomically replace READY members on compose', (tester) async {
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final fixture = HomeReadyMembersFixture(DateTime.now());
    var composed = false;
    var newlyReady = false;
    final feed = HomeFeedProvider(
        owner: () => 'fixture',
        fetch: ({cursor}) async => ApiSuccess(HomeFeedPage(
            items: composed
                ? [
                    HomeFeedCard(
                        id: 'episode:owner',
                        kind: 'episode',
                        detailId: 'owner',
                        startedAt: fixture.waiting.startedAt,
                        title: 'Combined fixture',
                        emoji: '',
                        preview: 'Combined notes',
                        status: 'completed',
                        homeStep: 'ready',
                        starred: false,
                        isLocked: false,
                        hasTasks: false,
                        memberCount: 4,
                        sources: const [],
                        summaryAvailable: true,
                        revision: 'composed')
                  ]
                : [
                    for (final member in fixture.members)
                      HomeFeedCard(
                          id: 'conversation:${member.id}',
                          kind: 'conversation',
                          detailId: member.id,
                          startedAt: member.startedAt,
                          title: member.structured.title,
                          emoji: '',
                          preview: member.structured.overview,
                          status: 'completed',
                          homeStep: newlyReady && member.id == fixture.members[2].id ? 'ready' : member.homeStep,
                          starred: false,
                          isLocked: false,
                          hasTasks: false,
                          memberCount: 1,
                          sources: const [],
                          summaryAvailable: member.homeStep == 'ready',
                          revision: 'waiting')
                  ],
            nextCursor: null,
            hasMore: false,
            truncated: false,
            generation: composed ? 'composed' : 'waiting')));
    addTearDown(feed.dispose);
    await feed.start();
    await _pumpHome(tester, [], feed: feed, withNavigation: true, detailItems: fixture.members);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(tester.widget<ProcessingConversationRow>(find.byType(ProcessingConversationRow)).count, 2);
    expect(find.text('Ready recording 1'), findsOneWidget);
    expect(find.text('Ready recording 2'), findsOneWidget);
    final aggregate = tester.widget<ProcessingConversationRow>(find.byType(ProcessingConversationRow));
    expect(aggregate.episode!.members.map((m) => m.id).toSet(), fixture.members.skip(2).map((m) => m.id).toSet());
    expect(aggregate.episode!.conversationIds.toSet(), fixture.members.skip(2).map((m) => m.id).toSet());
    await tester.tap(find.byKey(_processingKey));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    for (final member in fixture.members.take(2)) {
      expect(find.byKey(ValueKey('episode_member_${member.id}')), findsNothing);
    }
    for (final member in fixture.members.skip(2)) {
      expect(find.byKey(ValueKey('episode_member_${member.id}')), findsOneWidget);
    }
    newlyReady = true;
    await feed.refresh();
    await tester.pump();
    expect(find.byKey(ValueKey('episode_member_${fixture.members[2].id}')), findsNothing);
    expect(find.byKey(ValueKey('episode_member_${fixture.members[3].id}')), findsOneWidget);
    final history =
        Provider.of<ConversationProvider>(tester.element(find.byKey(const Key('episode_page'))), listen: false);
    final deleted = <String>[];
    history.conversationDeleteFetcherOverride = (id) async {
      deleted.add(id);
      return true;
    };
    await tester.tap(find.byKey(const Key('episode_more')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.text('Delete'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Delete 1 Conversation?'), findsOneWidget);
    await tester.tap(find.text('Delete').last);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(history.memoriesToDelete.keys.toSet(), {fixture.members[3].id});
    // The typed Home fixture nests Scaffolds; invoke the rendered Undo action
    // directly. The standalone destructive-scope suite verifies its tap path.
    tester
        .widget<TextButton>(find.descendant(of: find.byType(SnackBarAction), matching: find.byType(TextButton)))
        .onPressed!();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(history.memoriesToDelete, isEmpty);
    expect(deleted, isEmpty);
    expect(find.text('Ready recording 1'), findsOneWidget);
    expect(find.text('Ready recording 2'), findsOneWidget);
    composed = true;
    await feed.refresh();
    await tester.pump();
    expect(find.text('Combined fixture'), findsOneWidget);
    expect(find.text('Ready recording 1'), findsNothing);
    expect(find.text('Ready recording 2'), findsNothing);
    expect(find.byType(ProcessingConversationRow), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    debugDefaultTargetPlatformOverride = null;
  });

  TestWidgetsFlutterBinding.ensureInitialized();
  final previousVisibilityInterval = VisibilityDetectorController.instance.updateInterval;
  setUpAll(() async {
    Env.init(HomeFixtureEnv());
    PlatformManager.initializeForLocalHarness();
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    await _fonts();
  });
  tearDownAll(() => VisibilityDetectorController.instance.updateInterval = previousVisibilityInterval);

  for (final withLive in [false, true]) {
    for (final metadataOnly in [false, true]) {
      testWidgets('READY members are readable before compose, live=$withLive metadataOnly=$metadataOnly',
          (tester) async {
        final fixture = HomeReadyMembersFixture(DateTime.now());
        var current = fixture.waiting;
        final episodes = EpisodeProvider(
            fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: withLive ? fixture.live : null)),
            lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: current)),
            fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [current])));
        await episodes.refreshLive();
        episodes.debugSetHomeEpisodes([current]);
        final capture = withLive ? _LiveCapture() : null;
        if (capture != null) addTearDown(capture.dispose);
        final detailReads = <String>[];
        final boundary = await _pumpHome(tester, metadataOnly ? [] : [...fixture.members],
            episodeProvider: episodes,
            capture: capture,
            withNavigation: true,
            detailItems: fixture.members,
            onDetailFetch: detailReads.add);
        expect(find.text('Transcribing… · 2 recordings'), findsOneWidget);
        for (final member in fixture.members.take(2)) {
          final row = tester.widget<ConversationListItem>(find.byKey(ValueKey(member.id)));
          expect(row.homeEpisode, isNull, reason: 'temporary member opens its own notes');
          expect(row.conversation.structured.overview, member.structured.overview);
          expect(_top(tester, find.byKey(_processingKey)) < _top(tester, find.byKey(ValueKey(member.id))), isTrue);
        }
        {
          await tester.tap(find.byKey(ValueKey(fixture.members.first.id)));
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 400));
          final page = tester.widget<ConversationDetailPage>(find.byType(ConversationDetailPage));
          expect(page.conversation.id, fixture.members.first.id);
          expect(detailReads, contains(fixture.members.first.id), reason: 'metadata rows hydrate the real recording');
          expect(find.text(fixture.members.first.structured.overview), findsWidgets);
          Navigator.of(tester.element(find.byType(ConversationDetailPage))).pop();
          await tester.pump();
          await tester.pump(const Duration(milliseconds: 400));
        }
        await _capture(tester, boundary, 'ready-members-before-compose');
        current = fixture.composed;
        episodes.debugSetHomeEpisodes([current]);
        await tester.pump();
        expect(find.text('Combined episode fixture'), findsOneWidget);
        expect(find.byKey(_processingKey), findsNothing);
        for (final member in fixture.members) {
          expect(find.byKey(ValueKey(member.id)), findsNothing, reason: 'one frame replaces every temporary row');
        }
        final replacement = tester.widget<ConversationListItem>(find.byKey(ValueKey('episode:${current.id}')));
        expect(replacement.homeEpisode!.members.map((m) => m.id).toSet(), fixture.members.map((m) => m.id).toSet());
        await _capture(tester, boundary, 'ready-members-after-compose');
        await tester.pumpWidget(const SizedBox.shrink());
        episodes.invalidateHome();
      });
    }
  }

  for (final withPending in [false, true]) {
    testWidgets('stale ready and noise processing entries never bypass the fold, pending=$withPending', (tester) async {
      final now = DateTime.now();
      final ready = _conv('ready-stale', now, title: 'Finished fixture', homeStep: 'ready');
      final noise = _conv('noise-stale', now, homeStep: 'noise');
      final pending = _conv('pending', now, homeStep: 'transcribing');
      await _pumpHome(tester, [ready, noise, if (withPending) pending],
          processing: [ready, noise, if (withPending) pending]);
      expect(find.byKey(_processingKey), withPending ? findsOneWidget : findsNothing);
      expect(find.text('Finished fixture'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }

  for (final withLive in [false, true]) {
    for (final serverOnly in [false, true]) {
      testWidgets('five pending episode groups have one row with live=$withLive serverOnly=$serverOnly',
          (tester) async {
        final fixture = HomeOneProcessingFixture(DateTime.now(), serverOnly: serverOnly);
        final episodes = EpisodeProvider(
          fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: withLive ? fixture.live : null)),
          fetchPage: (from, to, {cursor}) async =>
              ApiSuccess(EpisodePageRead(enabled: true, episodes: fixture.episodes)),
        );
        await episodes.refreshLive();
        episodes.debugSetHomeEpisodes(fixture.episodes);
        final capture = withLive ? _LiveCapture() : null;
        if (capture != null) addTearDown(capture.dispose);
        final boundary = await _pumpHome(tester, [if (!serverOnly) ...fixture.pending, fixture.finished],
            episodeProvider: episodes, capture: capture, processing: serverOnly ? [] : fixture.pending);
        expect(find.byKey(_processingKey), findsOneWidget);
        expect(find.text('Transcribing… · 27 recordings'), findsOneWidget);
        final row = tester.widget<ProcessingConversationRow>(find.byType(ProcessingConversationRow));
        expect(row.episode!.members.map((m) => m.id).toSet(), fixture.pending.map((m) => m.id).toSet());
        expect(row.processingEpisodes.map((e) => e.id).toSet(), fixture.episodes.map((e) => e.id).toSet());
        expect(_top(tester, find.byKey(_processingKey)) < _top(tester, find.text('Finished episode fixture')), isTrue);
        if (withLive) {
          expect(_top(tester, find.byType(LiveEpisodeRow)) < _top(tester, find.byKey(_processingKey)), isTrue);
        }
        await _capture(tester, boundary, withLive ? 'one-row-with-live' : 'one-row-without-live');
        await tester.pumpWidget(const SizedBox.shrink());
        episodes.invalidateHome();
      });
    }
  }

  testWidgets('live episode owns its three closed processing recordings', (tester) async {
    final now = DateTime.now();
    final start = now.subtract(const Duration(minutes: 24));
    final members = [
      for (var i = 0; i < 3; i++) _conv('closed-$i', start.add(Duration(minutes: i * 5)), homeStep: 'transcribing')
    ];
    // Live and Home requests race: the live snapshot knows only the current
    // recording; the Home snapshot already includes the earlier closed members.
    final full = Episode(
        id: 'live',
        live: true,
        startedAt: start,
        lastActivityAt: now,
        conversationIds: members.map((m) => m.id).toList(),
        members: members);
    final latest = full.copyWith(conversationIds: ['current'], members: []);
    final episodes = EpisodeProvider(
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: latest)),
      fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [full])),
    );
    final capture = _LiveCapture();
    addTearDown(capture.dispose);
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init();
    await episodes.refreshLive();
    episodes.debugSetHomeEpisodes([full]);
    final boundary = await _pumpHome(tester, members, episodeProvider: episodes, capture: capture, processing: members);
    expect(find.byType(LiveEpisodeRow), findsOneWidget);
    expect(find.byKey(_processingKey), _baseline ? findsWidgets : findsNothing);
    await _capture(
        tester, boundary, _baseline ? '001-mobile-ios-home-overlap-before' : '002-mobile-ios-home-overlap-after');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('001-davids-home-today', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    DateTime at(DateTime day, int h, int m) => DateTime(day.year, day.month, day.day, h, m);
    const prov = 'server_minimum';
    final items = [
      // Today
      _conv('t-proc', at(today, 17, 0), length: const Duration(seconds: 11)),
      _conv('t-rec-938', at(today, 16, 38), title: 'Recording · 9:38 AM', provenance: prov),
      _conv('t-yeah', at(today, 13, 46), title: 'Yeah.', provenance: prov),
      _conv('t-brains', at(today, 13, 37),
          title: 'Building Company Brains With AI',
          overview: 'Fixture overview',
          length: const Duration(hours: 4),
          emoji: '🧠'),
      _conv('t-checkin', at(today, 0, 53),
          title: 'Check-In and Timer Search',
          overview: 'Fixture overview',
          length: const Duration(minutes: 12),
          emoji: '⏱️'),
      // Yesterday
      _conv('y-full', at(yesterday, 22, 47),
          title: 'That you were already full.', provenance: prov, length: const Duration(minutes: 6, seconds: 39)),
      _conv('y-mmhmm', at(yesterday, 22, 41),
          title: 'Mm-hmm.', provenance: prov, length: const Duration(minutes: 3, seconds: 52)),
      _conv('y-rec-337', at(yesterday, 22, 37),
          title: 'Recording · 3:37 PM', provenance: prov, length: const Duration(seconds: 58)),
      _conv('y-proc', at(yesterday, 22, 30), length: const Duration(minutes: 6, seconds: 31)),
      _conv('y-didnt', at(yesterday, 21, 57),
          title: "We didn't Know.", provenance: prov, length: const Duration(minutes: 28)),
      _conv('y-family', at(yesterday, 21, 21),
          title: 'Family Tensions and AI Consulting',
          overview: 'Fixture overview',
          length: const Duration(hours: 2, minutes: 12),
          emoji: '🧠'),
      _conv('y-pipeline', at(yesterday, 17, 38),
          title: 'Project Work and Pipeline Friction',
          overview: 'Fixture overview',
          length: const Duration(hours: 2),
          emoji: '🧩'),
      _conv('y-proc-2', at(yesterday, 17, 0), length: const Duration(seconds: 11)),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Yesterday'), findsOneWidget);
    // Today: one run of three unfinished rows, then the two finished rows.
    expect(find.byKey(_processingKey), findsOneWidget);
    expect(find.textContaining('$_transcribing · 3 recordings'), findsOneWidget);
    // Yesterday keeps its finished rows; the older processing runs live in Activity.
    expect(find.textContaining('$_transcribing · 5 recordings'), findsNothing);
    expect(find.textContaining(_transcribing), findsOneWidget);
    expect(find.text('Building Company Brains With AI'), findsOneWidget);
    expect(find.text('Check-In and Timer Search'), findsOneWidget);
    expect(find.text('Family Tensions and AI Consulting'), findsOneWidget);
    expect(find.text('Project Work and Pipeline Friction'), findsOneWidget);
    _expectAbsent([
      'Yeah.',
      'Mm-hmm.',
      'Recording · 9:38 AM',
      'Recording · 3:37 PM',
      "We didn't Know.",
      'That you were already full.'
    ]);
    expect(_top(tester, find.byKey(_processingKey).at(0)) < _top(tester, find.text('Building Company Brains With AI')),
        isTrue);

    await _capture(tester, boundary, '001-davids-home-today');
  });

  testWidgets('002-mixed-steps', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    const prov = 'server_minimum';
    final items = [
      _conv('done-0800', at(8, 0),
          title: 'Quarterly planning review', overview: 'Fixture', length: const Duration(hours: 1), emoji: '🧭'),
      _conv('empty-1000', at(10, 0), length: const Duration(seconds: 20)),
      _conv('prov-1005', at(10, 5), title: 'Okay so the plan is', provenance: prov, length: const Duration(minutes: 2)),
      _conv('prov-1010', at(10, 10), title: 'Yeah.', provenance: prov, length: const Duration(minutes: 1)),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.byKey(_processingKey), findsOneWidget);
    expect(find.textContaining('$_transcribing · 3 recordings'), findsOneWidget);
    expect(find.text(_processing), findsOneWidget);
    expect(find.text('Quarterly planning review'), findsOneWidget);
    _expectAbsent(['Okay so the plan is', 'Yeah.']);

    await _capture(tester, boundary, '002-mixed-steps');
  });

  testWidgets('003-failed-hidden', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    final items = [
      _conv('done-0900', at(9, 0),
          title: 'Design sync notes', overview: 'Fixture', length: const Duration(minutes: 40), emoji: '🧩'),
      _conv('fail-1100', at(11, 0),
          title: 'Failed fixture one', homeStep: 'failed', length: const Duration(minutes: 5)),
      _conv('fail-1200', at(12, 0),
          title: 'Failed fixture two', homeStep: 'failed', length: const Duration(minutes: 3)),
      _conv('done-1300', at(13, 0),
          title: 'Lunch with the team', overview: 'Fixture', length: const Duration(minutes: 30), emoji: '🍽️'),
    ];
    final boundary = await _pumpHome(tester, items);

    // Failed rows are hidden on Home the way noise is; Activity's Needs attention section owns them.
    expect(find.text('Design sync notes'), findsOneWidget);
    expect(find.text('Lunch with the team'), findsOneWidget);
    expect(find.byKey(_processingKey), findsNothing);
    _expectAbsent(['Failed fixture one', 'Failed fixture two', _couldntProcess, _processing]);

    await _capture(tester, boundary, '003-failed-hidden');
  });

  testWidgets('004-noise-hidden', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    final items = [
      _conv('done-0900', at(9, 0),
          title: 'Design sync notes', overview: 'Fixture', length: const Duration(minutes: 40), emoji: '🧩'),
      _conv('noise-1000', at(10, 0), title: 'Background hum', homeStep: 'noise', length: const Duration(seconds: 15)),
      _conv('noise-1100', at(11, 0), homeStep: 'noise', length: const Duration(seconds: 8)),
      _conv('done-1300', at(13, 0),
          title: 'Lunch with the team', overview: 'Fixture', length: const Duration(minutes: 30), emoji: '🍽️'),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.text('Design sync notes'), findsOneWidget);
    expect(find.text('Lunch with the team'), findsOneWidget);
    expect(find.byKey(_processingKey), findsNothing);
    expect(find.text(_couldntProcess), findsNothing);
    _expectAbsent(['Background hum']);

    await _capture(tester, boundary, '004-noise-hidden');
  });

  testWidgets('005-finished-keeps-one-processing-row', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    const prov = 'server_minimum';
    final items = [
      _conv('prov-0900', at(9, 0), title: 'Okay.', provenance: prov, length: const Duration(minutes: 3)),
      _conv('done-1200', at(12, 0),
          title: 'Middle finished review', overview: 'Fixture', length: const Duration(minutes: 30), emoji: '🧠'),
      _conv('prov-1500', at(15, 0), title: 'Recording · 3:00 PM', provenance: prov, length: const Duration(minutes: 1)),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.byKey(_processingKey), findsOneWidget);
    expect(find.text('Middle finished review'), findsOneWidget);
    expect(find.text(_processing), findsOneWidget);
    expect(find.textContaining(_transcribing), findsNWidgets(0));
    // All pending recordings share the first row; finished work keeps its own row.
    final runs = find.byKey(_processingKey);
    final late = _top(tester, runs.at(0));
    final middle = _top(tester, find.text('Middle finished review'));
    expect(late < middle, isTrue, reason: 'processing stays above the finished row');
    _expectAbsent(['Okay.', 'Recording · 3:00 PM']);

    await _capture(tester, boundary, '005-finished-keeps-one-row');
  });

  testWidgets('006-locked-row', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    const prov = 'server_minimum';
    final items = [
      _conv('proc-1500', at(15, 0), length: const Duration(seconds: 12)),
      _conv('locked-1400', at(14, 0),
          title: 'Locked recording',
          overview: 'Fixture',
          length: const Duration(minutes: 20),
          emoji: '🔒',
          isLocked: true),
      _conv('prov-1300', at(13, 0), title: 'Mm-hmm.', provenance: prov, length: const Duration(minutes: 2)),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.byKey(_processingKey), findsOneWidget);
    expect(find.text('Locked recording'), findsOneWidget);
    final runs = find.byKey(_processingKey);
    final late = _top(tester, runs.at(0));
    final locked = _top(tester, find.text('Locked recording'));
    expect(late < locked, isTrue, reason: 'processing stays above the locked row');
    _expectAbsent(['Mm-hmm.']);

    await _capture(tester, boundary, '006-locked-row');
  });

  testWidgets('007-all-processing', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    DateTime at(int h, int m) => DateTime(today.year, today.month, today.day, h, m);
    const prov = 'server_minimum';
    final items = [
      _conv('a', at(9, 0), length: const Duration(seconds: 9)),
      _conv('b', at(9, 20), length: const Duration(seconds: 14)),
      _conv('c', at(10, 0), title: 'Yeah.', provenance: prov, length: const Duration(minutes: 4)),
      _conv('d', at(10, 30), title: 'Recording · 10:30 AM', provenance: prov, length: const Duration(minutes: 2)),
      _conv('e', at(11, 0),
          title: 'Thank you.', provenance: prov, homeStep: 'writing_notes', length: const Duration(minutes: 1)),
    ];
    final boundary = await _pumpHome(tester, items);

    expect(find.byKey(_processingKey), findsOneWidget);
    expect(find.textContaining('$_transcribing · 5 recordings'), findsOneWidget);
    expect(find.text(_processing), findsOneWidget);
    _expectAbsent(['Yeah.', 'Recording · 10:30 AM', 'Thank you.']);

    await _capture(tester, boundary, '007-all-processing');
  });

  /// David's Home on 2026-11-06: nothing today yet, yesterday's junk settled to noise or
  /// failed (hidden), and Wednesday's finished rows.
  testWidgets('008-davids-home-nov6', (tester) async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    final wednesday = today.subtract(const Duration(days: 2));
    DateTime at(DateTime day, int h, int m) => DateTime(day.year, day.month, day.day, h, m);
    const prov = 'server_minimum';
    final items = [
      // Yesterday
      _conv('y-rec-337', at(yesterday, 22, 37),
          title: 'Recording · 3:37 PM', provenance: prov, homeStep: 'noise', length: const Duration(seconds: 58)),
      _conv('y-didnt', at(yesterday, 21, 57),
          title: "We didn't Know.", provenance: prov, homeStep: 'noise', length: const Duration(minutes: 28)),
      _conv('y-family', at(yesterday, 21, 21),
          title: 'Family Tensions and AI Consulting',
          overview: 'Fixture overview',
          length: const Duration(hours: 2, minutes: 12),
          emoji: '🧠'),
      _conv('y-pipeline', at(yesterday, 17, 38),
          title: 'Project Work and Pipeline Friction',
          overview: 'Fixture overview',
          length: const Duration(hours: 2),
          emoji: '🧩'),
      _conv('y-failed', at(yesterday, 17, 0), homeStep: 'failed', length: const Duration(seconds: 11)),
      _conv('y-rec-938', at(yesterday, 16, 38),
          title: 'Recording · 9:38 AM', provenance: prov, homeStep: 'noise', length: const Duration(seconds: 58)),
      _conv('y-yeah', at(yesterday, 13, 46),
          title: 'Yeah.', provenance: prov, homeStep: 'noise', length: const Duration(minutes: 4)),
      _conv('y-company', at(yesterday, 13, 37),
          title: 'Company OS', overview: 'Fixture overview', length: const Duration(hours: 4), emoji: '🧠'),
      // Wednesday
      _conv('w-dessert', at(wednesday, 22, 47),
          title: 'Dessert Talk', overview: 'Fixture overview', length: const Duration(minutes: 38), emoji: '🍰'),
      _conv('w-lunch-gpu', at(wednesday, 20, 12),
          title: 'Lunch, GPU Costs', overview: 'Fixture overview', length: const Duration(minutes: 72), emoji: '💻'),
      _conv('w-scattered', at(wednesday, 18, 40),
          title: 'Scattered Conversation Fragments',
          overview: 'Fixture overview',
          length: const Duration(minutes: 54),
          emoji: '🧩'),
      _conv('w-fragment', at(wednesday, 17, 55),
          title: 'Fragment of an Incomplete Conversation',
          overview: 'Fixture overview',
          length: const Duration(minutes: 47),
          emoji: '📝'),
      _conv('w-unresolved', at(wednesday, 17, 20),
          title: 'Unresolved Issue', overview: 'Fixture overview', length: const Duration(minutes: 33), emoji: '🔧'),
      _conv('w-product-relo', at(wednesday, 16, 50),
          title: 'Product, Relocation', overview: 'Fixture overview', length: const Duration(minutes: 65), emoji: '🧭'),
      _conv('w-rec-921', at(wednesday, 16, 21),
          title: 'Recording · 9:21 AM', provenance: prov, homeStep: 'noise', length: const Duration(seconds: 41)),
      _conv('w-rec-835', at(wednesday, 15, 35),
          title: 'Recording · 8:35 AM', provenance: prov, homeStep: 'noise', length: const Duration(seconds: 22)),
    ];
    final boundary = await _pumpHome(tester, items);

    // Nothing recorded today; the list starts at Yesterday and reaches back to Wednesday.
    expect(find.text('Today'), findsNothing);
    expect(find.text('Yesterday'), findsOneWidget);
    expect(find.text(DateFormat('EEE, MMM d').format(wednesday)), findsOneWidget);
    // The failed empty capture is hidden: no Processing row at all on this Home.
    expect(find.byKey(_processingKey), findsNothing);
    for (final title in [
      'Family Tensions and AI Consulting',
      'Project Work and Pipeline Friction',
      'Company OS',
      'Dessert Talk',
      'Lunch, GPU Costs',
      'Scattered Conversation Fragments',
      'Fragment of an Incomplete Conversation',
      'Unresolved Issue',
      'Product, Relocation',
    ]) {
      expect(find.text(title), findsOneWidget, reason: '"$title" is a finished row and must show');
    }
    _expectAbsent([
      'Recording · 3:37 PM',
      "We didn't Know.",
      'Recording · 9:38 AM',
      'Yeah.',
      'Recording · 9:21 AM',
      'Recording · 8:35 AM',
      _couldntProcess,
      _processing,
    ]);
    // Newest to oldest across the two days.
    final family = _top(tester, find.text('Family Tensions and AI Consulting'));
    final company = _top(tester, find.text('Company OS'));
    final dessert = _top(tester, find.text('Dessert Talk'));
    expect(family < company && company < dessert, isTrue);

    await _capture(tester, boundary, '008-davids-home-nov6');
  });
}
