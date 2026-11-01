import 'dart:collection';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_tab.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/omi_routes.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/transcript.dart';

class _ReadCounter extends ListBase<TranscriptSegment> {
  _ReadCounter(this.items);
  final List<TranscriptSegment> items;
  int reads = 0;
  @override
  int get length => items.length;
  @override
  set length(int value) => items.length = value;
  @override
  TranscriptSegment operator [](int index) {
    reads++;
    return items[index];
  }

  @override
  void operator []=(int index, TranscriptSegment value) => items[index] = value;
}

// All data and summary fetches are local. Flutter's test HTTP override also
// rejects network requests; no authenticated backend is used by this probe.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  for (final semanticsEnabled in [false, true]) {
    testWidgets('iOS detail push census (semantics=$semanticsEnabled)', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final segments = _ReadCounter(List.generate(
          1200,
          (i) => TranscriptSegment(
                id: 'route-$i',
                text: 'Line $i',
                speaker: 'SPEAKER_00',
                isUser: true,
                personId: null,
                start: i.toDouble(),
                end: i + 1.0,
                translations: const [],
              )));
      final conversation = ServerConversation(
        id: 'route-detail',
        createdAt: DateTime(2026, 10, 23),
        structured: Structured('Route detail', 'A **local** summary.'),
        transcriptSegments: segments,
      );
      final conversations = ConversationProvider(isSignedIn: () => false)
        ..conversations = [conversation]
        ..groupConversationsByDate()
        ..conversationDetailsFetcherOverride = (_) async => conversation;
      final apps = AppProvider();
      var appFetches = 0;
      final detail = ConversationDetailProvider(
        fetchEnabledSummaryApps: () async {
          appFetches++;
          return [];
        },
        fetchSuggestedSummaryApps: (_) async => [],
      )..setProviders(apps, conversations);
      final navigator = GlobalKey<NavigatorState>();
      late PageRoute<void> pushed;
      var readsBeforePostFrameInit = 0;
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: conversations),
          ChangeNotifierProvider.value(value: apps),
          ChangeNotifierProvider.value(value: detail),
          ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
          ChangeNotifierProvider(create: (_) => PeopleProvider(loadPeople: () async => null)),
        ],
        child: MaterialApp(
          navigatorKey: navigator,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Builder(
              builder: (context) => TextButton(
                    onPressed: () {
                      pushed = omiPageRoute<void>(builder: (_) => ConversationDetailPage(conversation: conversation))
                          as PageRoute<void>;
                      navigator.currentState!.push(pushed);
                      // Registered before page.initState registers its hydration
                      // callback: separates the shell frame from post-frame startup.
                      WidgetsBinding.instance.addPostFrameCallback((_) {
                        readsBeforePostFrameInit = segments.reads;
                      });
                    },
                    child: const Text('Open detail'),
                  )),
        ),
      ));
      await tester.pumpAndSettle();
      final builds = <String, int>{};
      final previous = debugOnRebuildDirtyWidget;
      debugOnRebuildDirtyWidget = (element, builtOnce) {
        final type = element.widget.runtimeType.toString();
        builds.update(type, (n) => n + 1, ifAbsent: () => 1);
        previous?.call(element, builtOnce);
      };
      try {
        segments.reads = 0;
        await tester.tap(find.text('Open detail'));
        await tester.pump();
        final firstFrameBuilds = builds.values.fold<int>(0, (sum, n) => sum + n);
        final firstFrameFetches = appFetches;
        final firstFrameReads = segments.reads;
        final firstFrameSummary = builds['SummaryTab'] ?? 0;
        final firstFrameTranscript = builds['TranscriptWidgets'] ?? 0;
        await tester.pump(const Duration(milliseconds: 16));
        final secondFrameSummary = builds['SummaryTab'] ?? 0;
        var transitionFrames = 1;
        while (pushed.animation!.status != AnimationStatus.completed && transitionFrames < 40) {
          await tester.pump(const Duration(milliseconds: 16));
          transitionFrames++;
        }
        // ignore: avoid_print
        print('DETAIL_ROUTE semantics=$semanticsEnabled first_frame_builds=$firstFrameBuilds '
            'before_post_frame_init_reads=$readsBeforePostFrameInit through_first_pump_reads=$firstFrameReads first_frame_app_fetches=$firstFrameFetches summary_builds=$firstFrameSummary->$secondFrameSummary '
            'transcript_builds=$firstFrameTranscript transition_16ms_frames=$transitionFrames opaque=${pushed.opaque}');
        // Opening the page validated timestamps pairwise: 2,881,201 reads for 1,200 lines.
        expect(firstFrameReads, lessThan(20 * 1200), reason: 'detail open must stay linear in transcript length');
        expect(find.byType(SummaryTab), findsOneWidget);
        expect(find.byType(TranscriptWidgets), findsNothing);
        expect(find.byType(TranscriptWidget), findsNothing);
        expect(transitionFrames, lessThanOrEqualTo(32));
        expect(pushed.opaque, isTrue);
      } finally {
        debugOnRebuildDirtyWidget = previous;
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump(const Duration(seconds: 1));
        detail.dispose();
        apps.dispose();
        conversations.dispose();
        debugDefaultTargetPlatformOverride = null;
      }
    }, semanticsEnabled: semanticsEnabled);
  }
}
