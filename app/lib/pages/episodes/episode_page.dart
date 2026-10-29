import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/episode_content.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A closed occasion. Its summary/tasks/moments are the live page's own content blocks;
/// its members use the existing conversation detail and hydration path.
class EpisodePage extends StatelessWidget {
  const EpisodePage({super.key, required this.episode});
  final Episode episode;

  @override
  Widget build(BuildContext context) {
    final dates = OmiDateFormat.of(context);
    final history = context.watch<ConversationProvider?>();
    final hidden = context.watch<EpisodeProvider?>()?.hiddenHomeMembers ?? const <String>{};
    final known = {for (final c in history?.conversations ?? const <ServerConversation>[]) c.id: c};
    final members = [for (final member in episode.members) known[member.id] ?? member]
        .where((m) =>
            !m.discarded &&
            !m.deleted &&
            !hidden.contains(m.id) &&
            !(history?.memoriesToDelete.containsKey(m.id) ?? false))
        .toList();
    final memberIds = members.map((m) => m.id).toSet();
    final items =
        episode.visibleItems.where((i) => i.conversationId == null || memberIds.contains(i.conversationId)).toList();
    final moments = episode.moments.where((m) => memberIds.contains(m.conversationId)).toList();
    final primary = members.firstOrNull;
    final title = episode.title.trim().isNotEmpty
        ? episode.title
        : primary == null
            ? context.l10n.conversationTab
            : conversationRowTitle(context, primary);
    final duration = episode.lastActivityAt.difference(episode.startedAt).inSeconds.clamp(0, 2147483647);
    return Scaffold(
      key: const Key('episode_page'),
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(leading: const OmiBackButton()),
      body: ListView(
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          Text(title, style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4)),
          const SizedBox(height: OmiSpacing.sm),
          Text(
              '${dates.weekdayDate(episode.startedAt)} · ${dates.timeRange(episode.startedAt, episode.lastActivityAt)} · ${OmiDuration.compact(duration, context.l10n)}',
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(height: OmiSpacing.lg),
          EpisodeBullets(episode.bullets),
          if (items.isNotEmpty) ...[
            EpisodeSectionTitle(context.l10n.tasks, count: items.length),
            EpisodeContentCard(children: [for (final item in items) EpisodeItemRow(item: item, now: DateTime.now())]),
          ],
          if (moments.isNotEmpty) ...[
            EpisodeSectionTitle(context.l10n.episodeMoments),
            EpisodeContentCard(
                children: [for (final moment in moments) EpisodeMomentRow(moment: moment, current: false)]),
          ],
          EpisodeSectionTitle(context.l10n.conversations),
          for (final member in members)
            Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.sm),
                child: ConversationListItem(
                  key: ValueKey('episode_member_${member.id}'),
                  conversation: member,
                  date: member.startedAt ?? member.createdAt,
                  conversationIdx: -1,
                  allowSelection: false,
                  embedded: true,
                  openEpisodeFromSearch: false,
                )),
        ],
      ),
    );
  }
}
