import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';

import '../../support/typed_conversation_screen.dart';

void main() {
  testWidgets('Home shows no previous-episode link; the closed episode stays reachable from the live episode page',
      (tester) async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    tester.view.physicalSize = const Size(800, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final now = DateTime(2026, 10, 24, 12);
    final closed = Episode(
      id: 'closed',
      live: false,
      startedAt: now,
      lastActivityAt: now,
      title: 'Retained meeting',
      bullets: const ['Retained running note'],
      conversationIds: const ['still-in-progress'],
    );
    final episodes = EpisodeProvider(
      clock: () => now,
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: closed)),
    )..debugSetLive(closed);
    final history = ConversationProvider(
      isSignedIn: () => false,
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    );
    addTearDown(episodes.dispose);
    addTearDown(history.dispose);
    await tester.pumpWidget(await buildTypedConversationScreen(history, episodes: episodes));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 250));
    expect(history.conversations, isEmpty);
    // Home never surfaces a previous-episode row (unapproved UI, 2026-10-25); the
    // Continues pill lives only on the live episode page.
    expect(find.byKey(const Key('previous_episode_pill')), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
