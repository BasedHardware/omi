import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'gen/home_feed_wire.g.dart' as wire;

/// A display projection, never a conversation detail or episode membership receipt.
/// Omitted source content remains unknown until the existing detail API hydrates it.
class HomeFeedCard {
  const HomeFeedCard(
      {required this.id,
      required this.kind,
      required this.detailId,
      required this.startedAt,
      DateTime? sortAt,
      this.finishedAt,
      required this.title,
      required this.emoji,
      required this.preview,
      required this.status,
      this.homeStep,
      required this.starred,
      required this.isLocked,
      required this.hasTasks,
      required this.memberCount,
      required this.sources,
      required this.summaryAvailable,
      required this.revision})
      : _sortAt = sortAt,
        assert(sortAt != null || startedAt != null);
  final String id, kind, detailId, title, emoji, preview, status;
  final DateTime? startedAt;
  final DateTime? _sortAt;
  DateTime get sortAt => _sortAt ?? startedAt!;
  final DateTime? finishedAt;
  final String? homeStep;
  final bool starred, isLocked, hasTasks, summaryAvailable;
  final int memberCount;
  final List<String> sources;
  final String revision;

  factory HomeFeedCard.fromJson(Map<String, dynamic> json) =>
      HomeFeedCard.fromGenerated(wire.GeneratedHomeFeedCard.fromJson(json));

  factory HomeFeedCard.fromGenerated(wire.GeneratedHomeFeedCard value) {
    if (value.kind != 'episode' && value.kind != 'conversation') {
      throw const FormatException('Invalid card kind');
    }
    return HomeFeedCard(
        id: value.id,
        kind: value.kind,
        detailId: value.detailId,
        sortAt: value.sortAt.toUtc(),
        startedAt: value.startedAt?.toUtc(),
        finishedAt: value.finishedAt?.toUtc(),
        title: value.title,
        emoji: value.emoji,
        preview: value.preview,
        status: value.status,
        homeStep: value.homeStep,
        starred: value.starred,
        isLocked: value.isLocked,
        hasTasks: value.hasTasks,
        memberCount: value.memberCount,
        sources: value.sources ?? const [],
        summaryAvailable: value.summaryAvailable,
        revision: value.revision);
  }

  Map<String, dynamic> toJson() => wire.GeneratedHomeFeedCard(
          id: id,
          kind: kind,
          detailId: detailId,
          sortAt: sortAt,
          startedAt: startedAt,
          finishedAt: finishedAt,
          title: title,
          emoji: emoji,
          preview: preview,
          status: status,
          homeStep: homeStep,
          starred: starred,
          isLocked: isLocked,
          hasTasks: hasTasks,
          memberCount: memberCount,
          sources: sources,
          summaryAvailable: summaryAvailable,
          revision: revision)
      .toJson();

  HomeFeedCard withoutText() => HomeFeedCard(
      id: id,
      kind: kind,
      detailId: detailId,
      startedAt: startedAt,
      sortAt: sortAt,
      finishedAt: finishedAt,
      title: '',
      emoji: '',
      preview: '',
      status: status,
      homeStep: homeStep,
      starred: starred,
      isLocked: isLocked,
      hasTasks: hasTasks,
      memberCount: memberCount,
      sources: sources,
      summaryAvailable: false,
      revision: revision);

  ServerConversation displaySeed() => ServerConversation(
      id: kind == 'episode' ? id : detailId,
      createdAt: sortAt,
      startedAt: startedAt,
      finishedAt: finishedAt,
      structured: Structured(isLocked ? '' : title, '', emoji: emoji),
      isLocked: isLocked,
      starred: starred,
      homeStep: homeStep,
      status:
          ConversationStatus.values.firstWhere((s) => s.name == status, orElse: () => ConversationStatus.processing));

  Episode episodeSeed() => Episode(
      id: detailId,
      live: false,
      startedAt: startedAt ?? sortAt,
      lastActivityAt: finishedAt ?? startedAt ?? sortAt,
      title: isLocked ? '' : title,
      emoji: emoji);
}

class HomeFeedPage {
  const HomeFeedPage(
      {required this.items,
      required this.nextCursor,
      required this.hasMore,
      required this.truncated,
      this.generation = ''});
  final List<HomeFeedCard> items;
  final String? nextCursor;
  final bool hasMore, truncated;
  final String generation;
  factory HomeFeedPage.fromJson(Map<String, dynamic> j) {
    if (j['generation'] is! String ||
        j['items'] is! List ||
        j['has_more'] is! bool ||
        j['truncated'] is! bool ||
        (j['next_cursor'] != null && j['next_cursor'] is! String)) {
      throw const FormatException('Invalid Home envelope');
    }
    final value = wire.GeneratedHomeFeedResponse.fromJson(j);
    final page = HomeFeedPage(
        items: [for (final item in value.items ?? <wire.GeneratedHomeFeedCard>[]) HomeFeedCard.fromGenerated(item)],
        nextCursor: value.nextCursor,
        hasMore: value.hasMore,
        truncated: value.truncated,
        generation: value.generation);
    if (page.hasMore && page.nextCursor == null) throw const FormatException('Missing continuation');
    return page;
  }
}
