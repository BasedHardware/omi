// Synthetic native acceptance target. No account, auth session or backend access.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/home_rows_health.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../test/helpers/home_ready_members_fixture.dart';
import '../test/helpers/home_fixture_env.dart';
import '../test/support/typed_conversation_screen.dart';

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

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  Env.init(HomeFixtureEnv());
  Env.overrideApiBaseUrl('');
  PlatformManager.initializeForLocalHarness();
  HomeRowsHealth.report = (_) {};
  const withLive = bool.fromEnvironment('HOME_ONE_ROW_FIXTURE_LIVE', defaultValue: true);
  const compact = bool.fromEnvironment('HOME_READY_COMPACT', defaultValue: true);
  final fixture = HomeReadyMembersFixture(DateTime.now());
  var current = fixture.waiting;
  final conversations = ConversationProvider(isSignedIn: () => false)
    ..isLoadingConversations = false
    ..conversations = [...fixture.members]
    ..groupConversationsByDate()
    ..conversationDetailsFetcherOverride = (id) async => fixture.members.where((m) => m.id == id).firstOrNull;
  final episodes = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: withLive ? fixture.live : null)),
    fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [current])),
    detail: (_) async => ApiSuccess(current),
    lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: current)),
  );
  await episodes.refreshLive();
  episodes.debugSetHomeEpisodes(compact ? [] : [current]);
  final feed = HomeFeedProvider(
      owner: () => 'synthetic-fixture',
      fetch: ({cursor}) async => ApiSuccess(HomeFeedPage(
          items: current.composed
              ? [
                  HomeFeedCard(
                      id: 'episode:${current.id}',
                      kind: 'episode',
                      detailId: current.id,
                      startedAt: current.startedAt,
                      finishedAt: current.lastActivityAt,
                      title: current.title,
                      emoji: '💬',
                      preview: current.lede,
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
                        finishedAt: member.finishedAt,
                        title: member.structured.title,
                        emoji: '💬',
                        preview: member.structured.overview,
                        status: 'completed',
                        homeStep: member.homeStep,
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
          generation: current.composed ? 'composed' : 'waiting')));
  if (compact) await feed.start();
  final apps = AppProvider();
  final detail =
      ConversationDetailProvider(fetchConversation: (id) async => fixture.members.where((m) => m.id == id).firstOrNull);
  detail.setProviders(apps, conversations);
  final store = PendingWorkStore(
    loadPending: () async => const ApiSuccess(
        PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
    loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
  );
  await store.refresh();
  final home = await buildTypedConversationScreen(conversations,
      episodes: episodes,
      feed: compact ? feed : null,
      pendingWork: store,
      captureProvider: withLive ? _LiveCapture() : null,
      theme: buildOmiTheme(brightness: Brightness.light));
  runApp(MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
        if (compact) ChangeNotifierProvider<HomeFeedProvider>.value(value: feed),
        ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider(create: (_) => FolderProvider()),
        ChangeNotifierProvider(create: (_) => IntegrationProvider()),
        ChangeNotifierProvider(create: (_) => UsageProvider()),
        ChangeNotifierProvider(create: (_) => MessageProvider()),
      ],
      child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.light),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Stack(fit: StackFit.expand, children: [
            home,
            Positioned(
                bottom: 24,
                right: 8,
                child: Directionality(
                    textDirection: TextDirection.ltr,
                    child: Material(
                        child: TextButton(
                            key: const Key('fixture_compose'),
                            onPressed: () async {
                              current = fixture.composed;
                              episodes.debugSetHomeEpisodes([current]);
                              if (compact) await feed.refresh();
                            },
                            child: const Text('Compose fixture'))))),
          ]))));
}
