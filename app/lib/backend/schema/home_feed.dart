import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';

/// A display projection, never a conversation detail or episode membership receipt.
class HomeFeedCard {
  const HomeFeedCard(
      {required this.id,
      required this.kind,
      required this.detailId,
      required this.startedAt,
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
      required this.revision});
  final String id, kind, detailId, title, emoji, preview, status;
  final DateTime startedAt;
  final DateTime? finishedAt;
  final String? homeStep;
  final bool starred, isLocked, hasTasks, summaryAvailable;
  final int memberCount;
  final List<String> sources;
  final String revision;

  factory HomeFeedCard.fromJson(Map<String, dynamic> j) {
    if (j['kind'] != 'episode' && j['kind'] != 'conversation') throw const FormatException('Invalid card kind');
    if (j['id'] is! String ||
        j['detail_id'] is! String ||
        j['started_at'] is! String ||
        j['title'] is! String ||
        j['preview'] is! String ||
        j['status'] is! String ||
        j['revision'] is! String ||
        j['member_count'] is! int ||
        j['sources'] is! List) {
      throw const FormatException('Invalid Home card');
    }
    return HomeFeedCard(
        id: j['id'],
        kind: j['kind'],
        detailId: j['detail_id'],
        startedAt: DateTime.parse(j['started_at']),
        finishedAt: j['finished_at'] == null ? null : DateTime.parse(j['finished_at']),
        title: j['title'],
        emoji: j['emoji'] as String,
        preview: j['preview'],
        status: j['status'],
        homeStep: j['home_step'] as String?,
        starred: j['starred'] as bool,
        isLocked: j['is_locked'] as bool,
        hasTasks: j['has_tasks'] as bool,
        memberCount: j['member_count'],
        sources: List<String>.from(j['sources']),
        summaryAvailable: j['summary_available'] as bool,
        revision: j['revision']);
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind,
        'detail_id': detailId,
        'started_at': startedAt.toUtc().toIso8601String(),
        'finished_at': finishedAt?.toUtc().toIso8601String(),
        'title': title,
        'emoji': emoji,
        'preview': preview,
        'status': status,
        'home_step': homeStep,
        'starred': starred,
        'is_locked': isLocked,
        'has_tasks': hasTasks,
        'member_count': memberCount,
        'sources': sources,
        'summary_available': summaryAvailable,
        'revision': revision
      };

  HomeFeedCard withoutText() => HomeFeedCard(
      id: id,
      kind: kind,
      detailId: detailId,
      startedAt: startedAt,
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
      createdAt: startedAt,
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
      startedAt: startedAt,
      lastActivityAt: finishedAt ?? startedAt,
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
    final page = HomeFeedPage(
        items: [for (final item in j['items']) HomeFeedCard.fromJson(Map<String, dynamic>.from(item))],
        nextCursor: j['next_cursor'],
        hasMore: j['has_more'],
        truncated: j['truncated'],
        generation: j['generation']);
    if (page.hasMore && page.nextCursor == null) throw const FormatException('Missing continuation');
    return page;
  }
}
