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
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/pages/episodes/episode_sections.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/sfpro_font_fixtures.dart';

/// A composed episode reads like a conversation summary: a lede, a section per moment with its
/// points, and follow-ups. With `--dart-define=EPISODE_COMPOSED_RENDER_OUTPUT=<dir>` it writes the PR
/// evidence PNGs; `EPISODE_COMPOSED_RENDER_FIXTURE=<json>` swaps in another episode (kept out of git).
const _output = String.fromEnvironment('EPISODE_COMPOSED_RENDER_OUTPUT');
const _fixture = String.fromEnvironment('EPISODE_COMPOSED_RENDER_FIXTURE');
final _boundary = GlobalKey();
final _at = DateTime(2026, 10, 30, 14, 56);

Episode _fictional() {
  final members = [
    ServerConversation(
        id: 'standup',
        createdAt: _at,
        startedAt: _at,
        structured: Structured('Launch checklist review', '', emoji: '🚀')),
    ServerConversation(
        id: 'lunch',
        createdAt: _at.add(const Duration(hours: 2)),
        startedAt: _at.add(const Duration(hours: 2)),
        structured: Structured('Lunch with Maya', '', emoji: '🥗')),
  ];
  return Episode(
    id: 'e',
    live: false,
    startedAt: _at,
    lastActivityAt: _at.add(const Duration(hours: 2, minutes: 40)),
    title: 'Launch prep and lunch with Maya',
    lede: 'Alex and Priya walked the launch checklist and moved the release to Thursday; '
        'over lunch Maya offered to run the beta survey.',
    bullets: const ['Alex and Priya walked the launch checklist and moved the release to Thursday.'],
    followUps: const ['Priya sends the updated checklist by Wednesday', 'Alex books the beta survey slot with Maya'],
    members: members,
    conversationIds: const ['standup', 'lunch'],
    moments: [
      EpisodeMoment(
        id: 'm1',
        conversationId: 'standup',
        startedAt: _at,
        endedAt: _at.add(const Duration(minutes: 18)),
        heading: 'Launch checklist',
        points: const [
          EpisodePoint('The release moves from Tuesday to Thursday.',
              details: ['Two signing certificates expire Monday and need renewal first.']),
          EpisodePoint('Onboarding copy still has three open review comments.', details: ['Priya owns them.']),
          EpisodePoint('Crash-free rate on the beta is 99.4%, above the 99% bar.'),
        ],
      ),
      EpisodeMoment(
        id: 'm2',
        conversationId: 'standup',
        startedAt: _at.add(const Duration(minutes: 41)),
        endedAt: _at.add(const Duration(minutes: 47)),
        heading: 'Pricing page',
        points: const [
          EpisodePoint('They agreed to drop the annual toggle for launch.',
              details: ['It confused two of five testers.', 'Revisit after the first month of data.']),
        ],
      ),
      EpisodeMoment(
        id: 'm3',
        conversationId: 'lunch',
        startedAt: _at.add(const Duration(hours: 2, minutes: 5)),
        endedAt: _at.add(const Duration(hours: 2, minutes: 32)),
        heading: 'Beta survey with Maya',
        points: const [
          EpisodePoint('Maya offered to run the beta survey through her research panel.',
              details: ['About 40 participants, results in a week.']),
          EpisodePoint('They compared notes on hiring a second designer.'),
        ],
      ),
    ],
  );
}

Episode _fromFixture(String path) {
  final json = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
  DateTime at(String clock) {
    final parts = clock.split(':').map(int.parse).toList();
    return DateTime(_at.year, _at.month, _at.day, parts[0], parts[1], parts.length > 2 ? parts[2] : 0);
  }

  final moments = [
    for (final (i, m) in (json['moments'] as List).cast<Map<String, dynamic>>().indexed)
      EpisodeMoment(
        id: 'm$i',
        conversationId: m['conversation'] as String,
        startedAt: at(m['start'] as String),
        endedAt: at(m['end'] as String),
        heading: m['heading'] as String,
        points: [
          for (final p in (m['points'] as List).cast<Map<String, dynamic>>())
            EpisodePoint(p['text'] as String, details: (p['details'] as List).cast<String>()),
        ],
      ),
  ];
  final ids = {for (final m in moments) m.conversationId}.toList();
  final members = [
    for (final (i, id) in ids.indexed)
      ServerConversation(
          id: id,
          createdAt: moments.firstWhere((m) => m.conversationId == id).startedAt,
          startedAt: moments.firstWhere((m) => m.conversationId == id).startedAt,
          structured: Structured(((json['members'] as List?)?.elementAtOrNull(i) as String?) ?? 'Conversation', '')),
  ];
  return Episode(
    id: 'fixture',
    live: false,
    startedAt: moments.first.startedAt,
    lastActivityAt: moments.last.endedAt,
    title: json['title'] as String,
    lede: json['lede'] as String,
    bullets: [json['lede'] as String],
    followUps: (json['follow_ups'] as List).cast<String>(),
    members: members,
    conversationIds: ids,
    moments: moments,
  );
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
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

Future<void> _capture(WidgetTester tester, String name) async {
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name').writeAsBytes(bytes!.buffer.asUint8List());
  });
}

/// The same episode a moment after it ended: the notes aren't written yet.
Episode _writing() {
  final done = _fictional();
  final now = DateTime.now();
  return Episode(
    id: done.id,
    live: false,
    startedAt: now.subtract(const Duration(hours: 1, minutes: 36)),
    lastActivityAt: now,
    closedAt: now,
    title: done.title,
    bullets: done.bullets,
    members: done.members,
    conversationIds: done.conversationIds,
    items: [
      EpisodeItem(
        id: 'i1',
        text: 'Send the updated checklist to Priya',
        createdAt: now,
        conversationId: 'standup',
        status: EpisodeItemStatus.kept,
      ),
    ],
  );
}

ServerConversation _rowFor(Episode episode) => ServerConversation(
    id: 'episode:${episode.id}',
    createdAt: episode.startedAt,
    startedAt: episode.startedAt,
    finishedAt: episode.lastActivityAt,
    structured: Structured(episode.title, '', emoji: '🚀'));

Future<void> _pump(WidgetTester tester, Episode episode, Brightness brightness, {Widget? home}) async {
  OmiColors.active = OmiColors.forBrightness(brightness);
  final history = ConversationProvider(isSignedIn: () => true)..conversations = [...episode.members];
  final episodes = EpisodeProvider()
    ..debugSetLive(null)
    ..debugSetHomeEpisodes([episode]);
  final connectivity = ConnectivityProvider();
  addTearDown(history.dispose);
  addTearDown(episodes.dispose);
  addTearDown(connectivity.dispose);
  await tester.pumpWidget(RepaintBoundary(
    key: _boundary,
    child: MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: history),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: connectivity),
      ],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: home ?? EpisodePage(episode: episode),
      ),
    ),
  ));
  await tester.pump();
  // The processing ring turns forever, so settling would never end.
  await tester.pump(const Duration(milliseconds: 400));
}

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await _loadFonts();
  });

  for (final brightness in [Brightness.light, Brightness.dark]) {
    testWidgets('a composed episode shows its lede, a section per moment and follow-ups (${brightness.name})',
        (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 1700);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final episode = _fixture.isEmpty ? _fictional() : _fromFixture(_fixture);
      await _pump(tester, episode, brightness);

      expect(find.byKey(const Key('episode_lede')), findsOneWidget);
      for (final moment in episode.moments) {
        expect(find.text(moment.heading), findsOneWidget);
        expect(find.byKey(ValueKey('episode_section_open_${moment.id}')), findsOneWidget);
      }
      if (_fixture.isEmpty) {
        expect(find.text('Two signing certificates expire Monday and need renewal first.'), findsOneWidget);
        expect(find.text('Follow-ups'), findsOneWidget);
        expect(find.text('Priya sends the updated checklist by Wednesday'), findsOneWidget);
        // Sections replace the separate Moments list on a composed episode.
        expect(find.text('Moments'), findsNothing);
      }
      expect(tester.takeException(), isNull);
      await _capture(
          tester, '00${brightness == Brightness.light ? 1 : 2}-mobile-ios-episode-composed-${brightness.name}.png');
      debugDefaultTargetPlatformOverride = null;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    });
  }

  for (final brightness in [Brightness.light, Brightness.dark]) {
    testWidgets('Home shows one row per stage, with no parts count (${brightness.name})', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 300);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final writing = _writing();
      final done = _fictional();
      await _pump(tester, done, brightness,
          home: Scaffold(
              body: Column(children: [
            ProcessingConversationRow(conversation: _rowFor(writing), episode: writing),
            ConversationListItem(
                key: const ValueKey('finished'),
                conversation: _rowFor(done),
                date: done.startedAt,
                conversationIdx: -1,
                homeEpisode: done),
          ])));
      expect(find.textContaining('Writing notes…'), findsOneWidget);
      expect(find.textContaining('1h 36m'), findsOneWidget);
      expect(find.textContaining('parts'), findsNothing);
      expect(tester.takeException(), isNull);
      await _capture(tester, '00${brightness == Brightness.light ? 3 : 4}-mobile-ios-home-rows-${brightness.name}.png');
      debugDefaultTargetPlatformOverride = null;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    });

    testWidgets('the page reads Writing notes while the notes are written (${brightness.name})', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await _pump(tester, _writing(), brightness);
      expect(find.byKey(const Key('episode_writing_notes')), findsOneWidget);
      expect(find.text('Summary'), findsOneWidget);
      expect(find.text('Transcript'), findsOneWidget);
      expect(find.text('Send the updated checklist to Priya'), findsOneWidget);
      expect(find.text('Alex and Priya walked the launch checklist and moved the release to Thursday.'), findsNothing,
          reason: 'draft notes wait for the summary');
      expect(tester.takeException(), isNull);
      await _capture(
          tester, '00${brightness == Brightness.light ? 5 : 6}-mobile-ios-episode-writing-${brightness.name}.png');
      debugDefaultTargetPlatformOverride = null;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
    });
  }

  testWidgets('a processing row opens the same page, which turns into the notes when they land', (tester) async {
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final writing = _writing();
    await _pump(tester, writing, Brightness.light,
        home: Scaffold(body: ProcessingConversationRow(conversation: _rowFor(writing), episode: writing)));
    await tester.tap(find.byKey(const Key('home_processing_row')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byKey(const Key('episode_page')), findsOneWidget);
    expect(find.byKey(const Key('episode_writing_notes')), findsOneWidget);
    Provider.of<EpisodeProvider>(tester.element(find.byKey(const Key('episode_page'))), listen: false)
        .debugSetHomeEpisodes([_fictional()]);
    await tester.pump();
    expect(find.byKey(const Key('episode_writing_notes')), findsNothing);
    expect(find.byKey(const Key('episode_lede')), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a row with no episode yet opens a page that still finds the notes when they land', (tester) async {
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final writing = _writing();
    await _pump(tester, writing, Brightness.light,
        home: Scaffold(body: ProcessingConversationRow(conversation: writing.members.first)));
    await tester.tap(find.byKey(const Key('home_processing_row')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byKey(const Key('episode_writing_notes')), findsOneWidget);
    Provider.of<EpisodeProvider>(tester.element(find.byKey(const Key('episode_page'))), listen: false)
        .debugSetHomeEpisodes([_fictional()]);
    await tester.pump();
    expect(find.byKey(const Key('episode_lede')), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a section opens its moment in the transcript', (tester) async {
    OmiColors.active = OmiColors.forBrightness(Brightness.light);
    final opened = <String>[];
    final moments = _fictional().moments;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: EpisodeSections(moments: moments, onOpenMoment: (m) => opened.add(m.id))),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('episode_section_open_m2')));
    expect(opened, ['m2']);
    expect(find.bySemanticsLabel('Open transcript'), findsNWidgets(3));
  });

  testWidgets('an uncomposed closed episode keeps its notes and Moments list', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final plain = _fictional();
    final episode = Episode(
      id: plain.id,
      live: false,
      startedAt: plain.startedAt,
      lastActivityAt: plain.lastActivityAt,
      title: plain.title,
      bullets: const ['A running note'],
      members: plain.members,
      conversationIds: plain.conversationIds,
      moments: [
        for (final m in plain.moments)
          EpisodeMoment(
              id: m.id,
              conversationId: m.conversationId,
              startedAt: m.startedAt,
              endedAt: m.endedAt,
              heading: m.heading),
      ],
    );
    await _pump(tester, episode, Brightness.light);
    expect(find.text('A running note'), findsOneWidget);
    expect(find.text('Moments'), findsOneWidget);
    expect(find.byKey(const Key('episode_lede')), findsNothing);
    debugDefaultTargetPlatformOverride = null;
  });
}
