import 'dart:async';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/home_rows.dart';
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
  const EpisodePage({
    super.key,
    required this.episode,
    this.processingAggregate = false,
    this.displaySeedOnly = false,
    this.processingEpisodes = const [],
  });
  final Episode episode;
  final bool displaySeedOnly;
  final bool processingAggregate;
  final List<Episode> processingEpisodes;

  /// Read current stores at the action boundary. A card/owner replacement or any
  /// settled/hidden state removes a recording from this aggregate immediately.
  /// Conflicting snapshots only narrow a destructive scope; they never expand it.
  List<ServerConversation> _currentPendingMembers(BuildContext context, Set<String> initialIds) {
    final history = context.read<ConversationProvider>();
    final episodes = context.read<EpisodeProvider?>();
    final sourceSeeds = [
      episode,
      ...processingEpisodes,
      ...?episodes?.homeEpisodes,
      for (final id in initialIds)
        if (episodes?.cachedEpisodeFor(id) case final source?) source,
    ];
    final sources = [
      ...sourceSeeds,
      for (final source in sourceSeeds)
        if (episodes?.openedEpisode(source.id) case final opened?) opened,
    ];
    final variants = <String, List<ServerConversation>>{};
    for (final c in [
      for (final source in sources) ...source.members,
      ...history.processingConversations,
      ...history.conversations
    ]) {
      (variants[c.id] ??= []).add(c);
    }
    final pending = <ServerConversation>[];
    for (final id in initialIds) {
      final versions = variants[id] ?? const <ServerConversation>[];
      if (history.memoriesToDelete.containsKey(id) ||
          (episodes?.hiddenHomeMembers.contains(id) ?? false) ||
          sources.any((s) => !s.live && s.composed && s.conversationIds.contains(id)) ||
          versions.any((m) =>
              m.discarded ||
              m.deleted ||
              m.isLocked ||
              m.homeStep == 'ready' ||
              m.homeStep == 'noise' ||
              homeStepOf(m) == HomeStep.failed ||
              (m.status == ConversationStatus.completed && homeStepOf(m) == null))) {
        continue;
      }
      final latest = versions.lastOrNull;
      if (latest == null) continue;
      final member = latest;
      if ({HomeStep.transcribing, HomeStep.writingNotes}.contains(homeStepOf(member))) pending.add(member);
    }
    return pending;
  }

  Future<void> _delete(BuildContext context, List<ServerConversation> displayedMembers) async {
    final authoritative = displaySeedOnly ? context.read<EpisodeProvider?>()?.openedEpisode(episode.id) : episode;
    if (authoritative == null) {
      OmiFeedback.error(context, context.l10n.somethingWentWrong);
      return;
    }
    final history = context.read<ConversationProvider>();
    final l10n = context.l10n;
    if (!context.read<ConnectivityProvider>().isConnected) {
      await showOmiAlert(
        context,
        title: l10n.unableToDeleteConversation,
        message: l10n.pleaseCheckInternetConnectionAndTryAgain,
      );
      return;
    }
    // A finished episode owns all its records. A processing collection owns only
    // its displayed pending members; source identity is navigation metadata.
    final ids = processingAggregate ? displayedMembers.map((m) => m.id).toSet() : authoritative.conversationIds.toSet();
    final known = {
      for (final c in authoritative.members) c.id: c,
      for (final c in history.conversations) c.id: c,
      for (final c in displayedMembers) c.id: c,
    };
    var targets = [
      for (final id in ids)
        if (!history.memoriesToDelete.containsKey(id))
          known[id] ??
              ServerConversation(id: id, createdAt: episode.startedAt, discarded: true, structured: Structured('', '')),
    ];
    if (targets.isEmpty) return;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.deleteConversationsTitle(targets.length),
      message: l10n.deleteConversationsMessage,
      confirmLabel: l10n.delete,
      destructive: true,
    );
    if (!confirmed || !context.mounted) return;
    if (processingAggregate) {
      final initialIds = targets.map((m) => m.id).toSet();
      final current = _currentPendingMembers(context, initialIds);
      if (current.length != initialIds.length) {
        OmiFeedback.info(context, context.l10n.processingDeleteScopeChanged);
        return;
      }
      // No await between the fresh scope and staging Delete/Undo. Undo receives
      // exactly these latest records, never the pre-confirmation snapshot.
      targets = current;
    }
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
    final seedAwaiting = displaySeedOnly && episodes?.openedEpisode(opened.id) == null;
    final openedMemberIds = opened.members.map((m) => m.id).toSet();
    final replacement = episodes?.openedEpisode(opened.id) ??
        episodes?.homeEpisodes
            .where((e) => opened.id.isEmpty ? e.conversationIds.any(openedMemberIds.contains) : e.id == opened.id)
            .firstOrNull;
    // One owner's finished notes can arrive on this page. A collection spanning
    // owners never adopts only the first; its source links remain independent.
    final episode = processingAggregate
        ? replacement != null &&
                replacement.composed &&
                replacement.conversationIds.toSet().containsAll(openedMemberIds)
            ? replacement
            : opened
        : replacement ?? opened;
    // A processing aggregate is a collection of owners, never the first matching
    // owner. Keep every recording and provide a link to each real episode's notes.
    final owners = {
      for (final source in processingEpisodes) source.id: source,
      if (processingAggregate)
        for (final source in episodes?.homeEpisodes ?? const <Episode>[])
          if (source.id.isNotEmpty && !source.live && source.conversationIds.any(openedMemberIds.contains))
            source.id: source,
    };
    final sources = [
      for (final source in owners.values)
        episodes?.openedEpisode(source.id) ??
            episodes?.homeEpisodes.where((e) => e.id == source.id).firstOrNull ??
            source,
    ];
    final known = {
      for (final source in sources)
        for (final c in source.members) c.id: c,
      for (final c in history?.processingConversations ?? const <ServerConversation>[]) c.id: c,
      for (final c in history?.conversations ?? const <ServerConversation>[]) c.id: c,
    };
    final retained = {
      for (final member in processingAggregate ? opened.members : episode.members) member.id: member,
    };
    final members = [
      for (final member in retained.values) known[member.id] ?? member,
    ]
        .where(
          (m) =>
              !m.discarded &&
              !m.deleted &&
              !hidden.contains(m.id) &&
              !(history?.memoriesToDelete.containsKey(m.id) ?? false) &&
              (!processingAggregate ||
                  (homeStepOf(m) != HomeStep.failed && m.homeStep != 'ready' && m.homeStep != 'noise' && !m.isLocked)),
        )
        .toList();
    final memberIds = members.map((m) => m.id).toSet();
    final items =
        episode.visibleItems.where((i) => i.conversationId == null || memberIds.contains(i.conversationId)).toList();
    final moments = episode.moments.where((m) => memberIds.contains(m.conversationId)).toList();
    final composed = episode.composed;
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
        seedAwaiting
            ? context.l10n.loading
            : '${dates.weekdayDate(episode.startedAt)} · ${dates.timeRange(episode.startedAt, episode.lastActivityAt)} · ${OmiDuration.compact(duration, context.l10n)}',
        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
      ),
    ];
    final memberRows = <Widget>[
      if (processingAggregate) _ProcessingSourceLinks(members: opened.members, sources: sources),
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
          ),
        ),
    ];
    return Scaffold(
      key: const Key('episode_page'),
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        actions: [
          PullDownButton(
            itemBuilder: (_) => [
              PullDownMenuItem(
                title: context.l10n.delete,
                iconWidget: FaIcon(FontAwesomeIcons.trashCan, size: 16, color: OmiColors.danger),
                isDestructive: true,
                onTap: () => _delete(context, members),
              ),
            ],
            buttonBuilder: (_, showMenu) => OmiIconButton.filled(
              key: const Key('episode_more'),
              icon: const FaIcon(FontAwesomeIcons.ellipsisVertical, size: 16),
              label: context.l10n.moreOptions,
              onPressed: showMenu,
            ),
          ),
        ],
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          Positioned.fill(
            child: seedAwaiting
                ? ListView(padding: const EdgeInsets.all(OmiSpacing.md), children: [
                    ...heading,
                    if (episodes?.openProblem(opened.id) != null)
                      OmiErrorState(
                          message: context.l10n.somethingWentWrong,
                          onRetry: () async {
                            await episodes?.openEpisode(opened.id);
                          })
                    else
                      const OmiLoadingState(),
                  ])
                : processing
                    ? _ProcessingBody(heading: heading, items: items, memberRows: memberRows)
                    : ListView(
                        padding: const EdgeInsets.all(OmiSpacing.md),
                        children: [
                          ...heading,
                          const SizedBox(height: OmiSpacing.lg),
                          if (composed) ...[
                            // A composed episode reads like a conversation's summary: a lede, then a section per moment.
                            if (episode.lede.trim().isNotEmpty)
                              Text(
                                episode.lede,
                                key: const Key('episode_lede'),
                                style: OmiType.callout.copyWith(height: 1.45),
                              ),
                            EpisodeSections(
                              moments: moments,
                              onOpenMoment: (moment) => _openMoment(context, moment, members),
                            ),
                            if (episode.followUps.isNotEmpty) ...[
                              EpisodeSectionTitle(context.l10n.episodeFollowUps),
                              EpisodeBullets(episode.followUps),
                            ],
                          ] else
                            EpisodeBullets(episode.bullets),
                          if (items.isNotEmpty) ...[
                            EpisodeSectionTitle(context.l10n.tasks, count: items.length),
                            EpisodeContentCard(
                              children: [for (final item in items) EpisodeItemRow(item: item, now: DateTime.now())],
                            ),
                          ],
                          if (!composed && moments.isNotEmpty) ...[
                            EpisodeSectionTitle(context.l10n.episodeMoments),
                            EpisodeContentCard(
                              children: [
                                for (final moment in moments) EpisodeMomentRow(moment: moment, current: false)
                              ],
                            ),
                          ],
                          EpisodeSectionTitle(context.l10n.conversations),
                          ...memberRows,
                        ],
                      ),
          ),
          // A late episode composes on this open; the server starts it on the read below.
          _OpenCompose(key: ValueKey('open-${episode.id}'), episode: episode),
        ],
      ),
    );
  }
}

/// The page's first frame asks the server for the episode once. A late episode's compose
/// starts on that read, and the provider folds the composed copy back into the page.
class _OpenCompose extends StatefulWidget {
  const _OpenCompose({super.key, required this.episode});
  final Episode episode;

  @override
  State<_OpenCompose> createState() => _OpenComposeState();
}

class _OpenComposeState extends State<_OpenCompose> {
  EpisodeProvider? _episodes;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final episodes = _episodes = context.read<EpisodeProvider?>();
      final episode = widget.episode;
      if (episodes == null || episode.id.isEmpty || episode.live) return;
      unawaited(episodes.openEpisode(episode.id));
    });
  }

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();

  @override
  void dispose() {
    _episodes?.cancelOpenEpisode(widget.episode.id);
    super.dispose();
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
            height: 12,
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          ),
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
                            Text(
                              l10n.episodeWritingNotesDetail,
                              style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                            ),
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
                          children: [for (final item in items) EpisodeItemRow(item: item, now: DateTime.now())],
                        ),
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

/// Compact cards omit owner membership. Resolve owners only after this page is
/// opened, and use the result for navigation only, never pending/Delete scope.
class _ProcessingSourceLinks extends StatefulWidget {
  const _ProcessingSourceLinks({required this.members, required this.sources});
  final List<ServerConversation> members;
  final List<Episode> sources;
  @override
  State<_ProcessingSourceLinks> createState() => _ProcessingSourceLinksState();
}

class _ProcessingSourceLinksState extends State<_ProcessingSourceLinks> {
  Future<List<Episode>>? _loaded;
  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loaded ??= _load(context.read<EpisodeProvider?>());
  }

  Future<List<Episode>> _load(EpisodeProvider? provider) async {
    if (provider == null) return [];
    final owner = SharedPreferencesUtil().uid;
    final found = <Episode>[...widget.sources];
    final loaded = <Episode>[];
    for (final member in widget.members) {
      if (!mounted || owner != SharedPreferencesUtil().uid) return [];
      if (found.any((source) => source.conversationIds.contains(member.id))) continue;
      try {
        final source = await provider.episodeFor(member.id);
        if (!mounted || owner != SharedPreferencesUtil().uid) return [];
        if (source != null && source.id.isNotEmpty && !found.any((e) => e.id == source.id)) {
          found.add(source);
          loaded.add(source);
        }
      } catch (_) {
        // Unassigned/unavailable owners never hide the actual recording links.
      }
    }
    return loaded;
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Episode>>(
      future: _loaded,
      builder: (context, snapshot) {
        final ids = widget.members.map((m) => m.id).toSet();
        final owners = {
          for (final source in [...?snapshot.data, ...widget.sources]) source.id: source
        };
        return Column(children: [
          for (final source in owners.values)
            if (source.conversationIds.any(ids.contains))
              ConversationListItem(
                key: ValueKey('processing_episode_${source.id}'),
                conversation: ServerConversation(
                  id: 'episode:${source.id}',
                  createdAt: source.startedAt,
                  startedAt: source.startedAt,
                  finishedAt: source.lastActivityAt,
                  structured: Structured(
                      source.title.trim().isEmpty ? context.l10n.wrappedProcessingDefault : source.title, '',
                      emoji: source.emoji),
                ),
                date: source.startedAt,
                conversationIdx: -1,
                homeEpisode: source,
                hasLinkedTasks: false,
                allowSelection: false,
                embedded: true,
              ),
        ]);
      });
}
