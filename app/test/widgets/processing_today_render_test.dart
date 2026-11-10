import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/past_processing_section.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../helpers/home_fixture_env.dart';
import '../helpers/sfpro_font_fixtures.dart';
import '../support/typed_conversation_screen.dart';

const _output = String.fromEnvironment('PROCESSING_TODAY_RENDER_OUTPUT');
const _phone = Size(393, 852);

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

PendingWorkStore _store(bool enabled, List<PendingWorkItem> pending) => PendingWorkStore(
      loadPending: () async => ApiSuccess(
          PendingWorkSnapshot(enabled: true, items: pending, attentionUnseenCount: 0, homeProcessingToday: enabled)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );

ServerConversation _conversation(String id, DateTime at, {String step = 'ready', String title = ''}) =>
    ServerConversation(
        id: id,
        createdAt: at,
        startedAt: at,
        finishedAt: at.add(const Duration(minutes: 12)),
        homeStep: step,
        structured: Structured(title, 'The team agreed on the next steps.'));

ThemeData _theme() {
  final theme = buildOmiTheme(brightness: Brightness.light);
  return theme.copyWith(
      appBarTheme: theme.appBarTheme
          .copyWith(titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display')));
}

Future<void> _capture(WidgetTester tester, GlobalKey key, String name) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
  expect(tester.takeException(), isNull);
  debugDefaultTargetPlatformOverride = null;
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final boundary = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await boundary.toImage(pixelRatio: 3);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name.png').writeAsBytes(data!.buffer.asUint8List());
    image.dispose();
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(HomeFixtureEnv());
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    await _fonts();
  });
  setUp(() {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    OmiColors.active = OmiPalette.light;
  });
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  for (final after in [false, true]) {
    final phase = after ? 'after' : 'before';
    for (final past in [false, true]) {
      testWidgets('$phase Home ${past ? 'past day' : 'today'}', (tester) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = _phone;
        addTearDown(tester.view.reset);
        final now = DateTime.now();
        final day = DateTime(now.year, now.month, now.day - (past ? 1 : 0));
        final rows = [
          _conversation('processing', day.add(const Duration(hours: 15)), step: 'transcribing'),
          _conversation('planning', day.add(const Duration(hours: 14)), title: 'Planning the week'),
          _conversation('coffee', day.add(const Duration(hours: 10)), title: 'Coffee with Maya'),
        ];
        final provider = ConversationProvider(
            isSignedIn: () => true,
            conversationListFetcher: () async => (items: rows, ok: true),
            dailySummariesChecker: () async => false)
          ..conversations = rows
          ..processingConversations = [rows.first]
          ..groupedConversations = {day: rows};
        final store = _store(after, []);
        await store.refresh();
        addTearDown(provider.dispose);
        addTearDown(store.dispose);
        final boundary = GlobalKey();
        await tester.pumpWidget(RepaintBoundary(
            key: boundary, child: await buildTypedConversationScreen(provider, pendingWork: store, theme: _theme())));
        final index = past ? (after ? '004' : '003') : (after ? '002' : '001');
        await _capture(tester, boundary, '$index-mobile-ios-home-${past ? 'past' : 'today'}-$phase');
        expect(find.byKey(const Key('home_processing_row')), past && after ? findsNothing : findsOneWidget);
        expect(find.text('Planning the week'), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      });
    }

    for (final empty in [false, true]) {
      testWidgets('$phase Activity ${empty ? 'empty' : 'past processing'}', (tester) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = _phone;
        addTearDown(tester.view.reset);
        final now = DateTime.now();
        final yesterday = DateTime(now.year, now.month, now.day - 1, 15, 42);
        final store = _store(after, [
          if (!empty)
            PendingWorkItem(
                id: 'conv:older',
                kind: 'conversation',
                state: 'transcribing',
                conversationIds: ['older'],
                startedAt: yesterday)
        ]);
        final monitor = CaptureWedgeMonitor(
            featureGate: () async => false,
            track: (_, __) {},
            bleRetry: (_) async {},
            appBuild: () => 'fixture',
            platform: () => 'ios');
        addTearDown(store.dispose);
        addTearDown(monitor.dispose);
        final boundary = GlobalKey();
        await tester.pumpWidget(RepaintBoundary(
            key: boundary,
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              theme: _theme(),
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: ActivityPage(
                  pendingWork: store,
                  captureWedgeMonitor: monitor,
                  seen: ActivitySeen(read: () => 0, write: (_) {}),
                  probeDreamReport: () async => false,
                  loadRecaps: () async => (items: <DailySummary>[], ok: true),
                  loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: []))),
            )));
        final index = empty ? (after ? '008' : '007') : (after ? '006' : '005');
        await _capture(tester, boundary, '$index-mobile-ios-activity-${empty ? 'empty' : 'processing'}-$phase');
        expect(find.byKey(const Key('activity_processing_older')), after && !empty ? findsOneWidget : findsNothing);
        await tester.pumpWidget(const SizedBox());
      });
    }
  }

  testWidgets('past processing row opens the source conversation', (tester) async {
    String? opened;
    final at = DateTime(2026, 11, 9, 15);
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
            body: PastProcessingSection(
                conversations: [_conversation('source-id', at, step: 'writing_notes')],
                openConversation: (_, id) async => opened = id))));
    await tester.tap(find.byKey(const ValueKey('activity_processing_source-id')));
    expect(opened, 'source-id');
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('Activity observes pending arrivals and completion even when recaps fail', (tester) async {
    var items = <PendingWorkItem>[];
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, items: items, attentionUnseenCount: 0)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    final monitor = CaptureWedgeMonitor(
        featureGate: () async => false,
        track: (_, __) {},
        bleRetry: (_) async {},
        appBuild: () => 'fixture',
        platform: () => 'ios');
    addTearDown(store.dispose);
    addTearDown(monitor.dispose);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: ActivityPage(
          pendingWork: store,
          captureWedgeMonitor: monitor,
          seen: ActivitySeen(read: () => 0, write: (_) {}),
          probeDreamReport: () async => false,
          loadRecaps: () async => (items: <DailySummary>[], ok: false),
          loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: []))),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity_processing_arrived')), findsNothing);
    final now = DateTime.now();
    items = [
      PendingWorkItem(
          id: 'conv:arrived',
          kind: 'conversation',
          state: 'summarizing',
          conversationIds: ['arrived'],
          startedAt: DateTime(now.year, now.month, now.day - 1, 15))
    ];
    await store.refresh();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity_processing_arrived')), findsOneWidget);
    expect(find.text('Writing notes…'), findsOneWidget);
    items = [];
    await store.refresh();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('activity_processing_arrived')), findsNothing);
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });
}
