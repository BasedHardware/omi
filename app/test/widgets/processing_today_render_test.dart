import 'package:omi/pages/activity/needs_attention_section.dart';
import 'dart:async';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/utils/local_day_rollover.dart';
import 'package:clock/clock.dart';
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
  // Render-only system font, never bundled in the app or required in CI.
  // Widget tests otherwise substitute square glyphs for iOS emoji badges.
  final emoji = File('/System/Library/Fonts/Apple Color Emoji.ttc');
  if (_output.isNotEmpty && emoji.existsSync()) {
    final loader = FontLoader('Evidence Emoji');
    loader.addFont(emoji.readAsBytes().then((bytes) => ByteData.sublistView(bytes)));
    await loader.load();
  }
}

PendingWorkStore _store(bool enabled, List<PendingWorkItem> pending, {List<AttentionItem> attention = const []}) =>
    PendingWorkStore(
      loadPending: () async => ApiSuccess(
          PendingWorkSnapshot(enabled: true, items: pending, attentionUnseenCount: 0, homeProcessingToday: enabled)),
      loadAttention: () async => ApiSuccess(AttentionItemsPage(enabled: true, items: attention, unseenCount: 0)),
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
      textTheme: theme.textTheme
          .copyWith(bodyMedium: theme.textTheme.bodyMedium?.copyWith(fontFamilyFallback: const ['Evidence Emoji'])),
      appBarTheme: theme.appBarTheme
          .copyWith(titleTextStyle: theme.appBarTheme.titleTextStyle?.copyWith(fontFamily: 'SF Pro Display')));
}

Future<void> _capture(WidgetTester tester, GlobalKey key, String name) async {
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 200));
  }
  expect(tester.takeException(), isNull);
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

void evidenceTest(String description, Future<void> Function(WidgetTester) body) {
  testWidgets(description, (tester) => withClock(Clock.fixed(DateTime(2026, 11, 10, 16)), () => body(tester)));
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

  testWidgets('unknown attention kinds remain display-only with conversation navigation', (tester) async {
    final store = _store(true, [], attention: const [
      AttentionItem(
          id: 'future',
          kind: 'future_kind',
          conversationId: 'future-conversation',
          title: 'New attention kind',
          retryable: true,
          seen: true,
          retryState: AttentionRetryState.none)
    ]);
    await store.refresh();
    addTearDown(store.dispose);
    String? opened;
    await tester.pumpWidget(MaterialApp(
        theme: _theme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: NeedsAttentionSection(store: store, openConversation: (_, id) async => opened = id))));
    expect(find.text('New attention kind'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Re-run notes'), findsNothing);
    await tester.tap(find.text('New attention kind'));
    expect(opened, 'future-conversation');
    expect(await store.retry(store.attention.single), isFalse);
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });

  for (final (index, title) in ['Planning follow-up', 'Actions captured', 'Meeting scheduled'].indexed) {
    evidenceTest('notes attention case 0${10 + index} keeps outputs and retries notes only', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = _phone;
      addTearDown(tester.view.reset);
      SharedPreferences.setMockInitialValues({'uid': 'fixture'});
      await SharedPreferencesUtil.init();
      final structured = Structured(title, '');
      if (index != 2) {
        structured.actionItems = [ActionItem('Send the design follow-up')];
      }
      if (index != 1) {
        structured.events = [Event('Planning meeting', DateTime(2026, 11, 11, 10), 30, created: true)];
      }
      final conversation = ServerConversation(
          id: 'kept-outputs',
          createdAt: clock.now(),
          homeStep: index == 0 ? 'failed' : 'noise',
          structured: structured);
      final before = jsonEncode(conversation.toJson());
      final provider = ConversationProvider(isSignedIn: () => false)..conversations = [conversation];
      final notes = AttentionItem(
          id: 'notes-case-0${10 + index}',
          kind: 'conversation_notes_failed_with_outputs',
          conversationId: conversation.id,
          title: title,
          retryable: true,
          seen: true,
          retryState: AttentionRetryState.none);
      var rejected = true;
      final sent = <String>[];
      final store = PendingWorkStore(
        loadPending: () async => const ApiSuccess(
            PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
        loadAttention: () async => ApiSuccess(AttentionItemsPage(
            enabled: true,
            items: [
              AttentionItem(
                  id: 'legacy',
                  kind: 'conversation_summary_failed',
                  conversationId: conversation.id,
                  retryable: true,
                  seen: true,
                  retryState: AttentionRetryState.none),
              notes
            ],
            unseenCount: 0)),
        retry: (id, {required idempotencyKey}) async {
          sent.add(id);
          if (rejected) {
            return const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409));
          }
          return ApiSuccess(AttentionRetryResult(itemId: id, state: AttentionRetryState.inProgress, operationId: 'op'));
        },
      );
      final monitor = CaptureWedgeMonitor(
          featureGate: () async => false,
          track: (_, __) {},
          bleRetry: (_) async {},
          appBuild: () => 'fixture',
          platform: () => 'ios');
      addTearDown(store.dispose);
      addTearDown(provider.dispose);
      addTearDown(monitor.dispose);
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(
          key: boundary,
          child: ChangeNotifierProvider.value(
              value: provider,
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
                      loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])))))));
      await _capture(tester, boundary, '0${19 + index}-mobile-ios-notes-case-0${10 + index}');
      expect(find.text(title), findsOneWidget);
      expect(find.text('Re-run notes'), findsOneWidget);
      expect(find.byKey(ValueKey('activity_failed_${conversation.id}')), findsNothing);
      await tester.tap(find.text('Re-run notes'));
      await tester.pumpAndSettle();
      expect(store.retryErrors, contains(notes.id));
      expect(find.textContaining('Something went wrong'), findsOneWidget);
      expect(find.text('Re-run notes'), findsOneWidget);
      rejected = false;
      await tester.tap(find.text('Re-run notes'));
      await tester.pumpAndSettle();
      expect(sent, [notes.id, notes.id]);
      expect(find.text(title), findsNothing);
      expect(jsonEncode(conversation.toJson()), before, reason: 'saved tasks/events must remain unchanged');
      expect(provider.conversations.single, same(conversation));
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    });
  }

  for (final after in [false, true]) {
    final phase = after ? 'after' : 'before';
    for (final past in [false, true]) {
      evidenceTest('$phase Home ${past ? 'past day' : 'today'}', (tester) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = _phone;
        addTearDown(tester.view.reset);
        final now = clock.now();
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
        debugDefaultTargetPlatformOverride = null;
      });
    }

    for (final empty in [false, true]) {
      evidenceTest('$phase Activity ${empty ? 'empty' : 'past processing'}', (tester) async {
        tester.view.devicePixelRatio = 1;
        tester.view.physicalSize = _phone;
        addTearDown(tester.view.reset);
        final now = clock.now();
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
        debugDefaultTargetPlatformOverride = null;
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

  evidenceTest('Activity observes pending arrivals and completion even when recaps fail', (tester) async {
    var items = <PendingWorkItem>[];
    final store = PendingWorkStore(
      loadPending: () async => ApiSuccess(
          PendingWorkSnapshot(enabled: true, items: items, attentionUnseenCount: 0, homeProcessingToday: true)),
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
    final now = clock.now();
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
  testWidgets('Home and Activity move a recording at midnight while open and cancel on dispose', (tester) async {
    var now = DateTime(2026, 11, 10, 23, 59, 59);
    await withClock(Clock(() => now), () async {
      final row = _conversation('midnight', now.subtract(const Duration(minutes: 10)), step: 'transcribing');
      final provider = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: [row], ok: true),
          dailySummariesChecker: () async => false)
        ..conversations = [row]
        ..processingConversations = [row]
        ..groupedConversations = {
          DateTime(2026, 11, 10): [row]
        };
      final store = _store(true, [
        PendingWorkItem(
            id: 'conv:midnight',
            kind: 'conversation',
            state: 'transcribing',
            conversationIds: ['midnight'],
            startedAt: row.startedAt)
      ]);
      await store.refresh();
      addTearDown(provider.dispose);
      addTearDown(store.dispose);
      await tester.pumpWidget(await buildTypedConversationScreen(provider, pendingWork: store, theme: _theme()));
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
      now = DateTime(2026, 11, 11, 0, 0, 2);
      await tester.pump(const Duration(seconds: 3));
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byKey(const Key('home_processing_row')), findsNothing);
      await tester.pumpWidget(const SizedBox());
      now = DateTime(2026, 11, 10, 23, 59, 59);
      final monitor = CaptureWedgeMonitor(
          featureGate: () async => false,
          track: (_, __) {},
          bleRetry: (_) async {},
          appBuild: () => 'fixture',
          platform: () => 'ios');
      addTearDown(monitor.dispose);
      await tester.pumpWidget(MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: ActivityPage(
              pendingWork: store,
              captureWedgeMonitor: monitor,
              seen: ActivitySeen(read: () => 0, write: (_) {}),
              probeDreamReport: () async => false,
              loadRecaps: () async => (items: <DailySummary>[], ok: true),
              loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])))));
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byKey(const Key('activity_processing_midnight')), findsNothing);
      now = DateTime(2026, 11, 11, 0, 0, 2);
      await tester.pump(const Duration(seconds: 3));
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byKey(const Key('activity_processing_midnight')), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(minutes: 2));
    });
    debugDefaultTargetPlatformOverride = null;
  });

  for (final after in [false, true]) {
    evidenceTest('episode ownership ${after ? 'after' : 'before'} delayed episode fetch', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = _phone;
      addTearDown(tester.view.reset);
      final now = clock.now();
      final rows = [
        for (final (id, title, hour) in [('planning', 'Planning the week', 14), ('coffee', 'Coffee with Maya', 10)])
          ServerConversation(
              id: id,
              createdAt: DateTime(now.year, now.month, now.day, hour),
              startedAt: DateTime(now.year, now.month, now.day, hour),
              structured: Structured(title, 'The team agreed on the next steps.'),
              homeStep: 'ready',
              episodeId: after ? 'shared-episode' : null)
      ];
      final provider = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: rows, ok: true),
          dailySummariesChecker: () async => false)
        ..conversations = rows
        ..groupedConversations = {DateTime(now.year, now.month, now.day): rows};
      final store = _store(true, []);
      await store.refresh();
      addTearDown(provider.dispose);
      addTearDown(store.dispose);
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(
          key: boundary, child: await buildTypedConversationScreen(provider, pendingWork: store, theme: _theme())));
      await _capture(
          tester, boundary, '${after ? '010' : '009'}-mobile-ios-episode-owner-${after ? 'after' : 'before'}');
      expect(find.text('Coffee with Maya'), after ? findsNothing : findsOneWidget);
      expect(find.text('Planning the week'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('civil clock jumps rebuild once and disposal cancels the check', (tester) async {
    var now = DateTime(2026, 11, 10, 12);
    var changes = 0;
    await withClock(Clock(() => now), () async {
      final rollover = LocalDayRollover(() => changes++);
      now = DateTime(2026, 11, 11, 2);
      await tester.pump(const Duration(minutes: 1));
      expect(changes, 1);
      await tester.pump(const Duration(minutes: 1));
      expect(changes, 1);
      rollover.cancel();
      now = DateTime(2026, 11, 12);
      await tester.pump(const Duration(minutes: 1));
      expect(changes, 1);
    });
    debugDefaultTargetPlatformOverride = null;
  });
  for (final after in [false, true]) {
    evidenceTest('failed conversation Home ${after ? 'after' : 'before'}', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = _phone;
      addTearDown(tester.view.reset);
      final at = clock.now().subtract(const Duration(hours: 8));
      final failed = ServerConversation(
          id: 'failed',
          createdAt: at,
          startedAt: at,
          status: ConversationStatus.processing,
          homeStep: 'failed',
          structured: Structured('Unfinished planning', ''));
      final ready = _conversation('ready', at.subtract(const Duration(hours: 1)), title: 'Coffee with Maya');
      final rows = [failed, ready];
      final provider = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: rows, ok: true),
          dailySummariesChecker: () async => false)
        ..conversations = rows
        ..processingConversations = [failed]
        ..groupedConversations = {DateTime(at.year, at.month, at.day): rows};
      final store = _store(after, []);
      await store.refresh();
      addTearDown(provider.dispose);
      addTearDown(store.dispose);
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(
          key: boundary, child: await buildTypedConversationScreen(provider, pendingWork: store, theme: _theme())));
      await _capture(tester, boundary, '${after ? '012' : '011'}-mobile-ios-home-failed-${after ? 'after' : 'before'}');
      expect(find.byWidgetPredicate((w) => w is ConversationListItem && w.conversation.id == 'failed'),
          after ? findsNothing : findsOneWidget);
      expect(find.text('Coffee with Maya'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    });

    evidenceTest('failed conversation Activity ${after ? 'after' : 'before'} and retry', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = _phone;
      addTearDown(tester.view.reset);
      SharedPreferences.setMockInitialValues({'uid': 'fixture'});
      await SharedPreferencesUtil.init();
      final at = clock.now().subtract(const Duration(hours: 8));
      final failed = ServerConversation(
          id: 'failed',
          createdAt: at,
          startedAt: at,
          homeStep: 'failed',
          status: ConversationStatus.processing,
          structured: Structured('Unfinished planning', ''));
      final provider = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: [failed], ok: true),
          dailySummariesChecker: () async => false)
        ..searchedConversations = [failed];
      final store = _store(after, []);
      final monitor = CaptureWedgeMonitor(
          featureGate: () async => false,
          track: (_, __) {},
          bleRetry: (_) async {},
          appBuild: () => 'fixture',
          platform: () => 'ios');
      addTearDown(provider.dispose);
      addTearDown(store.dispose);
      addTearDown(monitor.dispose);
      final retry = Completer<ServerConversation?>();
      var calls = 0;
      final boundary = GlobalKey();
      await tester.pumpWidget(RepaintBoundary(
          key: boundary,
          child: ChangeNotifierProvider<ConversationProvider>.value(
              value: provider,
              child: MaterialApp(
                  debugShowCheckedModeBanner: false,
                  theme: _theme(),
                  localizationsDelegates: AppLocalizations.localizationsDelegates,
                  supportedLocales: AppLocalizations.supportedLocales,
                  home: ActivityPage(
                      pendingWork: store,
                      captureWedgeMonitor: monitor,
                      reprocessConversation: (id) {
                        expect(id, 'failed');
                        calls++;
                        return retry.future;
                      },
                      seen: ActivitySeen(read: () => 0, write: (_) {}),
                      probeDreamReport: () async => false,
                      loadRecaps: () async => (items: <DailySummary>[], ok: true),
                      loadChanges: ({cursor}) async => const ApiSuccess(ReviewChangesPage(changes: [])))))));
      await _capture(
          tester, boundary, '${after ? '014' : '013'}-mobile-ios-activity-failed-${after ? 'after' : 'before'}');
      expect(find.byKey(const Key('activity_failed_failed')), after ? findsOneWidget : findsNothing);
      expect(find.text('Try Again'), after ? findsOneWidget : findsNothing);
      if (after) {
        await tester.tap(find.text('Try Again'));
        await tester.tap(find.text('Try Again'));
        expect(calls, 1);
        await tester.pump();
        retry.complete(_conversation('failed', at, title: 'Planning complete'));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('activity_failed_failed')), findsNothing);
        expect(provider.conversations.single.structured.title, 'Planning complete');
      }
      await tester.pumpWidget(const SizedBox());
      debugDefaultTargetPlatformOverride = null;
    });
  }

  evidenceTest('failed Activity retry errors remain visible and can be retried again', (tester) async {
    final failed = ServerConversation(
        id: 'retry-error', createdAt: clock.now(), homeStep: 'failed', structured: Structured('Unfinished notes', ''));
    final store = _store(true, []);
    await store.refresh();
    final monitor = CaptureWedgeMonitor(
        featureGate: () async => false,
        track: (_, __) {},
        bleRetry: (_) async {},
        appBuild: () => 'fixture',
        platform: () => 'ios');
    addTearDown(store.dispose);
    addTearDown(monitor.dispose);
    var attempts = 0;
    String? opened;
    await tester.pumpWidget(MaterialApp(
        theme: _theme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
            body: NeedsAttentionSection(
                store: store,
                captureMonitor: monitor,
                failedConversations: [failed],
                openConversation: (_, id) async => opened = id,
                reprocess: (_) async {
                  attempts++;
                  throw StateError('offline');
                }))));
    for (var i = 1; i <= 2; i++) {
      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();
      expect(attempts, i);
      expect(find.byKey(const Key('activity_failed_retry-error')), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    }
    expect(opened, isNull);
    await tester.tap(find.text('Unfinished notes'));
    expect(opened, 'retry-error');
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });
  evidenceTest('locked failed Activity rows keep the title redacted', (tester) async {
    final failed = ServerConversation(
        id: 'locked',
        createdAt: clock.now(),
        isLocked: true,
        status: ConversationStatus.failed,
        structured: Structured('Private notes', ''));
    final store = _store(true, []);
    await store.refresh();
    final monitor = CaptureWedgeMonitor(
        featureGate: () async => false,
        track: (_, __) {},
        bleRetry: (_) async {},
        appBuild: () => 'fixture',
        platform: () => 'ios');
    addTearDown(store.dispose);
    addTearDown(monitor.dispose);
    await tester.pumpWidget(MaterialApp(
        theme: _theme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
            body: NeedsAttentionSection(store: store, captureMonitor: monitor, failedConversations: [failed]))));
    expect(find.text('Private notes'), findsNothing);
    expect(find.text('Processing Failed'), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    debugDefaultTargetPlatformOverride = null;
  });
}
