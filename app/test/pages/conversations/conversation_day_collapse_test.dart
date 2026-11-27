import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/processing_conversation_row.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/components/omi_spinner.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../../support/typed_conversation_screen.dart';

class _Recordings extends ChangeNotifier implements LocalRecordingsProvider {
  _Recordings(this.recordings);

  @override
  final List<LocalRecording> recordings;

  @override
  bool isPlaying(LocalRecording recording) => false;

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final previousVisibilityInterval = VisibilityDetectorController.instance.updateInterval;
  setUpAll(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);
  tearDownAll(() => VisibilityDetectorController.instance.updateInterval = previousVisibilityInterval);

  testWidgets('days collapse and expand without changing their conversations', (tester) async {
    final semantics = tester.ensureSemantics();
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    final conversations = [
      for (final (id, title, date) in [
        ('today', 'Today conversation', today.add(const Duration(hours: 10))),
        ('yesterday', 'Yesterday conversation', today.subtract(const Duration(days: 1)).add(const Duration(hours: 10))),
      ])
        ServerConversation(
          id: id,
          createdAt: date,
          structured: Structured(title, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        ),
    ];
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: conversations, ok: true),
      isSignedIn: () => true,
    )
      ..conversations = conversations
      ..processingConversations = [
        ServerConversation(
          id: 'processing',
          createdAt: DateTime.now(),
          structured: Structured('', ''),
          status: ConversationStatus.processing,
        ),
      ]
      ..groupConversationsByDate();
    addTearDown(provider.dispose);
    final recordings = _Recordings([
      for (final state in [LocalRecordingState.pending, LocalRecordingState.failed])
        LocalRecording(
          fileName: '${state.name}.bin',
          filePath: '/tmp/${state.name}.bin',
          timerStart: today.millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          frameSize: 160,
          sizeBytes: 1024,
          seconds: 1,
          state: state,
        ),
    ]);
    addTearDown(recordings.dispose);

    await tester.pumpWidget(await buildTypedConversationScreen(provider, recordingsProvider: recordings));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));

    final dayKey = ValueKey('collapse_day_${today.toIso8601String()}');
    expect(find.byTooltip('Collapse'), findsNWidgets(2));
    expect(tester.getSize(find.byKey(dayKey)).width, greaterThanOrEqualTo(44));
    expect(tester.getSize(find.byKey(dayKey)).height, greaterThanOrEqualTo(44));
    final todayToggle = tester.getSemantics(find.byKey(dayKey)).getSemanticsData();
    final yesterday = DateTime(today.year, today.month, today.day - 1);
    final yesterdayKey = ValueKey('collapse_day_${yesterday.toIso8601String()}');
    final yesterdayToggle = tester.getSemantics(find.byKey(yesterdayKey)).getSemanticsData();
    expect(todayToggle.label, contains('Today'));
    expect(todayToggle.label, contains('Collapse'));
    expect(todayToggle.hasAction(ui.SemanticsAction.tap), isTrue);
    expect(todayToggle.flagsCollection.isButton, isTrue);
    expect(todayToggle.flagsCollection.isExpanded, ui.Tristate.isTrue);
    expect(yesterdayToggle.label, contains('Yesterday'));
    expect(yesterdayToggle.label, contains('Collapse'));
    expect(yesterdayToggle.flagsCollection.isExpanded, ui.Tristate.isTrue);
    expect(find.byType(ConversationListItem), findsNWidgets(2));
    expect(find.text('Today conversation'), findsOneWidget);
    expect(find.text('Yesterday conversation'), findsOneWidget);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(find.byType(RecordingListItem), findsNWidgets(2));

    final yesterdayRow = find.text('Yesterday conversation');
    final expandedY = tester.getTopLeft(yesterdayRow).dy;
    await tester.tap(find.byKey(dayKey));
    await tester.pump();
    expect(find.byTooltip('Expand'), findsOneWidget);
    final collapsedToggle = tester.getSemantics(find.byKey(dayKey)).getSemanticsData();
    expect(collapsedToggle.label, contains('Today'));
    expect(collapsedToggle.label, contains('Expand'));
    expect(collapsedToggle.flagsCollection.isExpanded, ui.Tristate.isFalse);
    expect(tester.getTopLeft(yesterdayRow).dy, expandedY);
    await tester.pump(const Duration(milliseconds: 125));
    final halfwayY = tester.getTopLeft(yesterdayRow).dy;
    expect(halfwayY, lessThan(expandedY));
    expect(find.text('Today conversation'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 125));
    final collapsedY = tester.getTopLeft(yesterdayRow).dy;
    expect(collapsedY, lessThan(halfwayY));
    expect(find.text('Today conversation'), findsNothing);
    expect(find.text('Yesterday conversation'), findsOneWidget);
    expect(find.byType(ConversationListItem), findsOneWidget);
    expect(find.byType(ProcessingConversationRow), findsOneWidget);
    expect(find.byType(RecordingListItem), findsNWidgets(2));
    expect(provider.conversations.map((conversation) => conversation.id), containsAll(['today', 'yesterday']));

    await tester.tap(find.byKey(dayKey));
    await tester.pump();
    expect(tester.getTopLeft(yesterdayRow).dy, collapsedY);
    await tester.pump(const Duration(milliseconds: 125));
    expect(tester.getTopLeft(yesterdayRow).dy, greaterThan(collapsedY));
    expect(tester.getTopLeft(yesterdayRow).dy, lessThan(expandedY));
    await tester.pump(const Duration(milliseconds: 125));
    expect(tester.getTopLeft(yesterdayRow).dy, expandedY);
    expect(find.text('Today conversation'), findsOneWidget);
    expect(find.text('Yesterday conversation'), findsOneWidget);

    tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    await tester.pump();
    await tester.tap(find.byKey(dayKey));
    await tester.pump();
    expect(find.text('Today conversation'), findsNothing);
    expect(tester.getTopLeft(yesterdayRow).dy, collapsedY);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('right-to-left day action announces its localized date and action', (tester) async {
    final semantics = tester.ensureSemantics();
    final today = DateUtils.dateOnly(DateTime.now());
    await tester.pumpWidget(MaterialApp(
      locale: const Locale('ar'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: DateListItem(date: today, isFirst: true, onToggle: () {})),
    ));
    await tester.pump();

    final key = ValueKey('collapse_day_${today.toIso8601String()}');
    final data = tester.getSemantics(find.byKey(key)).getSemanticsData();
    final day = tester.widget<Text>(find.descendant(of: find.byType(DateListItem), matching: find.byType(Text))).data!;
    expect(data.label, contains(day));
    expect(data.label, contains('طيّ'));
    expect(data.flagsCollection.isExpanded, ui.Tristate.isTrue);
    semantics.dispose();
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('recording-only day has no collapse control or collapsed pagination mode', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final recordings = _Recordings([
      LocalRecording(
        fileName: 'recording.bin',
        filePath: '/tmp/recording.bin',
        timerStart: today.millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        frameSize: 160,
        sizeBytes: 1024,
        seconds: 1,
        state: LocalRecordingState.pending,
      ),
    ]);
    addTearDown(recordings.dispose);

    await tester.pumpWidget(await buildTypedConversationScreen(provider, recordingsProvider: recordings));
    await tester.pump();

    expect(find.byType(RecordingListItem), findsOneWidget);
    expect(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')), findsNothing);
    expect(find.byType(OmiButton), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('collapsed days load older conversations only when requested', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    ServerConversation conversation(String id, DateTime date) => ServerConversation(
          id: id,
          createdAt: date,
          structured: Structured(id, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        );
    final firstPage = List.generate(50, (index) => conversation('conversation-$index', today));
    final pageReady = Completer<void>();
    var requests = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: firstPage, ok: true),
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      requests++;
      await pageReady.future;
      return (items: [conversation('older', today.subtract(const Duration(days: 1)))], ok: true, truncated: false);
    };
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    await tester.runAsync(() => provider.fetchConversations());
    await tester.pumpWidget(screen);
    await tester.pump();

    await tester.tap(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    expect(requests, 0);
    expect(find.text('Load More'), findsOneWidget);
    final button = find.byKey(const Key('conversations_show_more'));
    final size = tester.getSize(button);
    expect(size.height, greaterThanOrEqualTo(48));

    await tester.tap(button);
    await tester.pump();
    expect(tester.getSize(button), size);
    expect(find.descendant(of: button, matching: find.byType(OmiSpinner)), findsOneWidget);
    await tester.tap(button);
    await tester.pump();
    expect(requests, 1);
    pageReady.complete();
    await tester.pump();
    expect(provider.conversations.any((conversation) => conversation.id == 'older'), isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('scrolling a long list with a collapsed day does not prefetch the next page', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    final yesterday = today.subtract(const Duration(days: 1));
    ServerConversation conversation(String id, DateTime date) => ServerConversation(
          id: id,
          createdAt: date,
          structured: Structured(id, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        );
    final firstPage = [
      for (var i = 0; i < 5; i++) conversation('today-$i', today),
      for (var i = 0; i < 45; i++) conversation('yesterday-$i', yesterday),
    ];
    var requests = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: firstPage, ok: true),
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      requests++;
      return (items: [conversation('older', yesterday.subtract(const Duration(days: 1)))], ok: true, truncated: false);
    };
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    await tester.runAsync(() => provider.fetchConversations());
    await tester.pumpWidget(screen);
    await tester.pump();

    await tester.tap(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    for (var i = 0; i < 6; i++) {
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -3000));
      await tester.pump();
    }
    expect(requests, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('collapsed Home card days load older cards only when requested', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    HomeFeedCard card(String id, DateTime at) => HomeFeedCard(
          id: 'conversation:$id',
          kind: 'conversation',
          detailId: id,
          startedAt: at,
          title: id,
          emoji: '',
          preview: '',
          status: 'completed',
          homeStep: 'ready',
          starred: false,
          isLocked: false,
          hasTasks: false,
          memberCount: 1,
          sources: const [],
          summaryAvailable: true,
          revision: 'fixture',
        );
    final cursors = <String?>[];
    final nextPageReady = Completer<void>();
    final feed = HomeFeedProvider(
      owner: () => 'fixture',
      fetch: ({cursor}) async {
        cursors.add(cursor);
        if (cursor == 'next') await nextPageReady.future;
        return ApiSuccess(HomeFeedPage(
          // The newest page ends beyond the seven-day warm window, so only the button loads more.
          items: cursor == null
              ? [
                  card('new', today.add(const Duration(hours: 9))),
                  card('old', today.subtract(const Duration(days: 10)))
                ]
              : [card('older', today.subtract(const Duration(days: 11)))],
          nextCursor: cursor == null ? 'next' : null,
          hasMore: cursor == null,
          truncated: false,
          generation: 'fixture',
        ));
      },
    );
    addTearDown(feed.dispose);
    final provider = ConversationProvider(isSignedIn: () => false)
      ..isLoadingConversations = false
      ..groupConversationsByDate();
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider, feed: feed);
    await tester.runAsync(feed.start);
    await tester.pumpWidget(screen);
    await tester.pump();
    expect(cursors, [null]);

    await tester.tap(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    expect(find.text('new'), findsNothing);
    expect(find.text('old'), findsOneWidget);
    expect(find.text('Load More'), findsOneWidget);
    final button = find.byKey(const Key('conversations_show_more_cards'));
    final size = tester.getSize(button);
    await tester.tap(button);
    await tester.pump();
    expect(tester.getSize(button), size);
    expect(find.descendant(of: button, matching: find.byType(OmiSpinner)), findsOneWidget);
    await tester.tap(button);
    await tester.pump();
    expect(cursors, [null, 'next']);
    nextPageReady.complete();
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(cursors, [null, 'next']);
    expect(find.text('Load More'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a failed search page leaves Show more retryable', (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final today = DateUtils.dateOnly(DateTime.now());
    ServerConversation conversation(String id) => ServerConversation(
          id: id,
          createdAt: today,
          structured: Structured(id, 'Overview', emoji: '💬', category: 'work'),
          status: ConversationStatus.completed,
        );
    final pages = <int?>[];
    final provider = ConversationProvider(
      conversationSearchResultFetcher: (query,
          {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async {
        pages.add(page);
        if (page == null) {
          return ConversationSearchResult(
            items: [conversation('first')],
            currentPage: 1,
            totalPages: 2,
            outcome: ConversationSearchResultOutcome.success,
          );
        }
        // The first attempt at page 2 fails; the retry succeeds.
        if (pages.length == 2) return const ConversationSearchResult.failure(statusCode: 503);
        return ConversationSearchResult(
          items: [conversation('second')],
          currentPage: 2,
          totalPages: 2,
          outcome: ConversationSearchResultOutcome.success,
        );
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final screen = await buildTypedConversationScreen(provider);
    await tester.pumpWidget(screen);
    await tester.runAsync(() => provider.searchConversations('query'));
    await tester.pump();

    // The short list prefetches page 2 on its own and that attempt fails; collapsing then makes Show more manual.
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(pages, [null, 2]);
    expect(provider.currentSearchPage, 1);

    await tester.tap(find.byKey(ValueKey('collapse_day_${today.toIso8601String()}')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    await tester.tap(find.byKey(const Key('conversations_show_more')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    expect(pages, [null, 2, 2]);
    expect(provider.currentSearchPage, 2);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
