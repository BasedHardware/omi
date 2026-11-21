import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'home_rows.dart';

/// Compact cards carry their own pending step, never episode membership. The
/// server keeps recordings standalone until the composed owner replaces them.
List<HomeRow> buildHomeCardRows(List<HomeFeedCard> cards, List<ServerConversation> localPending,
    {required DateTime now,
    required String processingTitle,
    Set<String> liveIds = const {},
    bool processingTodayOnly = true}) {
  final cardIds = cards.where((c) => c.kind == 'conversation').map((c) => c.detailId).toSet();
  final ownerIds = cards.where((c) => c.kind == 'episode').map((c) => c.detailId).toSet();
  final seeds = [
    for (final card in cards)
      // A compact episode card is a finished display projection, not a pending
      // member or an authority for any destructive action.
      card.kind == 'episode' ? card.displaySeed().withHomeStep('ready') : localHomeProcessingEntry(card.displaySeed()),
    for (final member in localPending)
      if (!cardIds.contains(member.id) && !ownerIds.contains(member.episodeId) && !liveIds.contains(member.id))
        // Local placeholders cannot tell us that note writing has started.
        // An explicit server step wins, including ready/noise/failed.
        localHomeProcessingEntry(member),
  ];
  final rows = [
    for (final seed in seeds)
      if (!seed.deleted &&
          !seed.discarded &&
          !isHomeNoise(seed) &&
          homeStepOf(seed) != HomeStep.failed &&
          (!processingTodayOnly ||
              homeStepOf(seed) == null ||
              localHomeDay(seed.startedAt ?? seed.createdAt) == localHomeDay(now)))
        HomeRow(seed),
  ]..sort((a, b) {
      final order = b.startedAt.compareTo(a.startedAt);
      return order == 0 ? a.conversation.id.compareTo(b.conversation.id) : order;
    });
  return foldProcessingRuns(rows, processingTitle: processingTitle, processingDay: localHomeDay(now));
}
