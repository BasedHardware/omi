// Synthetic native acceptance target. No account, auth session or backend access.
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversations/home_rows_health.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../test/helpers/home_one_processing_fixture.dart';
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
  const serverOnly = bool.fromEnvironment('HOME_ONE_ROW_SERVER_ONLY');
  final fixture = HomeOneProcessingFixture(DateTime.now(), serverOnly: serverOnly);
  final conversations = ConversationProvider(isSignedIn: () => false)
    ..isLoadingConversations = false
    ..conversations = [if (!serverOnly) ...fixture.pending, fixture.finished]
    ..processingConversations = serverOnly ? [] : fixture.pending
    ..groupConversationsByDate();
  final episodes = EpisodeProvider(
    fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: withLive ? fixture.live : null)),
    fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: fixture.episodes)),
    detail: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
  );
  await episodes.refreshLive();
  episodes.debugSetHomeEpisodes(fixture.episodes);
  final store = PendingWorkStore(
    loadPending: () async => const ApiSuccess(
        PendingWorkSnapshot(enabled: true, items: [], attentionUnseenCount: 0, homeProcessingToday: true)),
    loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
  );
  await store.refresh();
  final home = await buildTypedConversationScreen(conversations,
      episodes: episodes,
      pendingWork: store,
      captureProvider: withLive ? _LiveCapture() : null,
      theme: buildOmiTheme(brightness: Brightness.light));
  runApp(MultiProvider(providers: [
    ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
    ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
    ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
  ], child: home));
}
