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
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/pages/episodes/live_episode_row.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../helpers/home_fixture_env.dart';
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
    CaptureProvider? capture,
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
  await tester.pumpWidget(RepaintBoundary(
    key: boundary,
    child: await buildTypedConversationScreen(
      conversations,
      pendingWork: store,
      episodes: episodes,
      captureProvider: capture,
      initializePreferences: false,
      theme: buildOmiTheme(brightness: Brightness.light),
    ),
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
  TestWidgetsFlutterBinding.ensureInitialized();
  final previousVisibilityInterval = VisibilityDetectorController.instance.updateInterval;
  setUpAll(() async {
    Env.init(HomeFixtureEnv());
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    await _fonts();
  });
  tearDownAll(() => VisibilityDetectorController.instance.updateInterval = previousVisibilityInterval);

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

  testWidgets('005-finished-breaks-run', (tester) async {
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

    expect(find.byKey(_processingKey), findsNWidgets(2));
    expect(find.text('Middle finished review'), findsOneWidget);
    expect(find.text(_processing), findsNWidgets(2));
    expect(find.textContaining(_transcribing), findsNWidgets(0));
    // Newest run first, the finished row between them, the earliest run last.
    final runs = find.byKey(_processingKey);
    final late = _top(tester, runs.at(0));
    final middle = _top(tester, find.text('Middle finished review'));
    final early = _top(tester, runs.at(1));
    expect(late < middle && middle < early, isTrue, reason: 'the finished row must split the two runs');
    _expectAbsent(['Okay.', 'Recording · 3:00 PM']);

    await _capture(tester, boundary, '005-finished-breaks-run');
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

    expect(find.byKey(_processingKey), findsNWidgets(2));
    expect(find.text('Locked recording'), findsOneWidget);
    final runs = find.byKey(_processingKey);
    final late = _top(tester, runs.at(0));
    final locked = _top(tester, find.text('Locked recording'));
    final early = _top(tester, runs.at(1));
    expect(late < locked && locked < early, isTrue, reason: 'the locked row keeps its own place between runs');
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
