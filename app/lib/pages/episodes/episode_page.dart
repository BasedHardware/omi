import 'dart:async';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/episode_content.dart';
import 'package:omi/pages/episodes/episode_sections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;

/// A closed occasion, from the moment it ends: the same page while its notes are being written
/// (Summary and Transcript tabs, then a page of sections). Its summary/tasks/moments are the live
/// page's own content blocks; its members use the existing conversation detail and hydration path.
class EpisodePage extends StatelessWidget {
  const EpisodePage({super.key, required this.episode});
  final Episode episode;

  Future<void> _delete(BuildContext context) async {
    final history = context.read<ConversationProvider>();
    final l10n = context.l10n;
    if (!context.read<ConnectivityProvider>().isConnected) {
      await showOmiAlert(context,
          title: l10n.unableToDeleteConversation, message: l10n.pleaseCheckInternetConnectionAndTryAgain);
      return;
    }
    // conversationIds includes discarded members; the visible list intentionally does not.
    final known = {for (final c in episode.members) c.id: c, for (final c in history.conversations) c.id: c};
    final targets = [
      for (final id in episode.conversationIds.toSet())
        if (!history.memoriesToDelete.containsKey(id))
          known[id] ??
              ServerConversation(id: id, createdAt: episode.startedAt, discarded: true, structured: Structured('', '')),
    ];
    if (targets.isEmpty) return;
    final confirmed = await showOmiConfirm(context,
        title: l10n.deleteConversationsTitle(targets.length),
        message: l10n.deleteConversationsMessage,
        confirmLabel: l10n.delete,
        destructive: true);
    if (!confirmed || !context.mounted) return;
    final listContext = Navigator.of(context).context;
    Navigator.pop(context);
    unawaited(deleteConversationsWithUndo(listContext, targets));
  }

  /// A moment opens in its conversation's transcript, at the moment.
  void _openMoment(BuildContext context, EpisodeMoment moment, List<ServerConversation> members) {
    final conversation = members.where((m) => m.id == moment.conversationId).firstOrNull;
    if (conversation == null) return;
    OmiHaptics.selection();
    routeToPage(
      context,
      ConversationDetailPage(
        conversation: conversation,
        initialTab: ConversationTab.transcript,
        initialSeekStart: moment.startOffset,
        initialSeekEnd: moment.endOffset > moment.startOffset ? moment.endOffset : null,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dates = OmiDateFormat.of(context);
    final history = context.watch<ConversationProvider?>();
    final episodes = context.watch<EpisodeProvider?>();
    final hidden = episodes?.hiddenHomeMembers ?? const <String>{};
    // The page outlives the row that opened it: the finished notes land here, too.
    // A row with no episode yet opens a stand-in with no id; its recording finds the real one.
    final opened = this.episode;
    final episode = episodes?.homeEpisodes
            .where(
                (e) => opened.id.isEmpty ? e.conversationIds.any(opened.conversationIds.contains) : e.id == opened.id)
            .firstOrNull ??
        opened;
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
    final composed = moments.any((m) => m.points.isNotEmpty);
    final primary = members.firstOrNull;
    final title = episode.title.trim().isNotEmpty
        ? episode.title
        : primary == null
            ? context.l10n.conversationTab
            : conversationRowTitle(context, primary);
    final duration = episode.lastActivityAt.difference(episode.startedAt).inSeconds.clamp(0, 2147483647);
    final processing = !composed && (episode.live || episode.awaitingSummary(DateTime.now()));
    final heading = <Widget>[
      Text(title, style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4)),
      const SizedBox(height: OmiSpacing.sm),
      Text(
          '${dates.weekdayDate(episode.startedAt)} · ${dates.timeRange(episode.startedAt, episode.lastActivityAt)} · ${OmiDuration.compact(duration, context.l10n)}',
          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
    ];
    final memberRows = <Widget>[
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
    ];
    return Scaffold(
      key: const Key('episode_page'),
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(leading: const OmiBackButton(), actions: [
        PullDownButton(
          itemBuilder: (_) => [
            PullDownMenuItem(
              title: context.l10n.delete,
              iconWidget: FaIcon(FontAwesomeIcons.trashCan, size: 16, color: OmiColors.danger),
              isDestructive: true,
              onTap: () => _delete(context),
            )
          ],
          buttonBuilder: (_, showMenu) => OmiIconButton.filled(
            key: const Key('episode_more'),
            icon: const FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16),
            label: context.l10n.moreOptions,
            onPressed: showMenu,
          ),
        ),
      ]),
      body: processing
          ? _ProcessingBody(heading: heading, items: items, memberRows: memberRows)
          : ListView(
              padding: const EdgeInsets.all(OmiSpacing.md),
              children: [
                ...heading,
                const SizedBox(height: OmiSpacing.lg),
                if (composed) ...[
                  // A composed episode reads like a conversation's summary: a lede, then a section per moment.
                  if (episode.lede.trim().isNotEmpty)
                    Text(episode.lede, key: const Key('episode_lede'), style: OmiType.callout.copyWith(height: 1.45)),
                  EpisodeSections(moments: moments, onOpenMoment: (moment) => _openMoment(context, moment, members)),
                  if (episode.followUps.isNotEmpty) ...[
                    EpisodeSectionTitle(context.l10n.episodeFollowUps),
                    EpisodeBullets(episode.followUps),
                  ],
                ] else
                  EpisodeBullets(episode.bullets),
                if (items.isNotEmpty) ...[
                  EpisodeSectionTitle(context.l10n.tasks, count: items.length),
                  EpisodeContentCard(
                      children: [for (final item in items) EpisodeItemRow(item: item, now: DateTime.now())]),
                ],
                if (!composed && moments.isNotEmpty) ...[
                  EpisodeSectionTitle(context.l10n.episodeMoments),
                  EpisodeContentCard(
                      children: [for (final moment in moments) EpisodeMomentRow(moment: moment, current: false)]),
                ],
                EpisodeSectionTitle(context.l10n.conversations),
                ...memberRows,
              ],
            ),
    );
  }
}

/// While the notes are being written: the card says so, tasks already read as tasks, and the
/// recordings behind it open on the Transcript tab.
class _ProcessingBody extends StatelessWidget {
  const _ProcessingBody({required this.heading, required this.items, required this.memberRows});

  final List<Widget> heading;
  final List<EpisodeItem> items;
  final List<Widget> memberRows;

  Widget _skeleton(double widthFactor) => Padding(
        padding: const EdgeInsets.only(top: OmiSpacing.xs),
        child: FractionallySizedBox(
          alignment: AlignmentDirectional.centerStart,
          widthFactor: widthFactor,
          child: Container(
              height: 12, decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll)),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return DefaultTabController(
      length: 2,
      child: Builder(
        builder: (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.sm),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: heading),
            ),
            ConversationDetailTabs(controller: DefaultTabController.of(context), onTap: (_) {}, showVisibility: false),
            Expanded(
              child: TabBarView(
                children: [
                  ListView(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    children: [
                      Container(
                        key: const Key('episode_writing_notes'),
                        padding: const EdgeInsets.all(OmiSpacing.md),
                        decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const OmiActivityRing(active: true, diameter: 16, child: SizedBox.shrink()),
                                const SizedBox(width: OmiSpacing.xs),
                                Expanded(child: Text(l10n.episodeWritingNotes, style: OmiType.headline)),
                              ],
                            ),
                            const SizedBox(height: 2),
                            Text(l10n.episodeWritingNotesDetail,
                                style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                            const SizedBox(height: OmiSpacing.xs),
                            _skeleton(0.92),
                            _skeleton(0.82),
                            _skeleton(0.56),
                          ],
                        ),
                      ),
                      if (items.isNotEmpty) ...[
                        EpisodeSectionTitle(l10n.tasks, count: items.length),
                        EpisodeContentCard(
                            children: [for (final item in items) EpisodeItemRow(item: item, now: DateTime.now())]),
                      ],
                    ],
                  ),
                  ListView(
                    key: const Key('episode_processing_transcript'),
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    children: memberRows,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
