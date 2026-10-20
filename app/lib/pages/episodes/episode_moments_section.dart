import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A finished conversation's Moments: the stretches of speech its episode was made of, collapsed
/// under one row. Shown only when the episode had more than one moment, so a one-moment episode
/// reads exactly like today's conversation page. [onOpenConversation] opens a moment recorded in
/// another conversation of the same episode.
class EpisodeMomentsSection extends StatefulWidget {
  const EpisodeMomentsSection({super.key, required this.conversationId, this.onOpenConversation});

  final String conversationId;
  final ValueChanged<String>? onOpenConversation;

  @override
  State<EpisodeMomentsSection> createState() => _EpisodeMomentsSectionState();
}

class _EpisodeMomentsSectionState extends State<EpisodeMomentsSection> {
  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    final episodes = context.read<EpisodeProvider?>();
    if (episodes != null) unawaited(episodes.episodeFor(widget.conversationId));
  }

  @override
  void didUpdateWidget(covariant EpisodeMomentsSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId) {
      _expanded = false;
      final episodes = context.read<EpisodeProvider?>();
      if (episodes != null) unawaited(episodes.episodeFor(widget.conversationId));
    }
  }

  @override
  Widget build(BuildContext context) {
    final episodes = context.watch<EpisodeProvider?>();
    final episode = episodes?.cachedEpisodeFor(widget.conversationId);
    if (episode == null || episode.live || episode.moments.length < 2) return const SizedBox.shrink();
    return EpisodeMomentsList(
      episode: episode,
      conversationId: widget.conversationId,
      expanded: _expanded,
      onToggle: () {
        OmiHaptics.selection();
        setState(() => _expanded = !_expanded);
      },
      onOpenConversation: widget.onOpenConversation,
    );
  }
}

/// The collapsible Moments card itself, separated from its data source for tests and renders.
class EpisodeMomentsList extends StatelessWidget {
  const EpisodeMomentsList({
    super.key,
    required this.episode,
    required this.conversationId,
    required this.expanded,
    required this.onToggle,
    this.onOpenConversation,
  });

  final Episode episode;
  final String conversationId;
  final bool expanded;
  final VoidCallback onToggle;
  final ValueChanged<String>? onOpenConversation;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final first = episode.moments.first;
    final summary = '${dates.time(first.startedAt)} · ${l10n.episodeMomentsCount(episode.moments.length)}';
    final rows = <Widget>[
      Semantics(
        button: true,
        expanded: expanded,
        label: '${l10n.episodeMoments}, $summary',
        excludeSemantics: true,
        child: InkWell(
          key: const Key('episode_moments_toggle'),
          borderRadius: OmiRadius.lgAll,
          onTap: onToggle,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 48),
            child: Row(
              children: [
                Expanded(child: Text(summary, style: OmiType.callout)),
                Icon(
                  expanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                  color: OmiColors.textTertiary,
                ),
              ],
            ),
          ),
        ),
      ),
      if (expanded)
        for (final moment in episode.moments) _row(context, moment),
    ];
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.lg),
      child: Column(
        key: const Key('episode_moments_section'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            // Flush with the summary text above it, like the page's other section titles.
            padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
            child: Text(l10n.episodeMoments, style: OmiType.headline),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows),
          ),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, EpisodeMoment moment) {
    final elsewhere = moment.conversationId != conversationId && onOpenConversation != null;
    final heading = moment.heading.isEmpty ? episode.title : moment.heading;
    final row = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 44),
      child: Row(
        children: [
          SizedBox(
            width: 64,
            child: Text(
              OmiDateFormat.of(context).time(moment.startedAt),
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
          ),
          Expanded(child: Text(heading, style: OmiType.callout, maxLines: 2, overflow: TextOverflow.ellipsis)),
          Text(
            EpisodePresentation.runningLength(moment.duration, context.l10n),
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
          // Every row keeps the chevron's slot, so the lengths line up whether or not a row opens.
          SizedBox(
            width: 22,
            child: elsewhere
                ? Icon(Icons.chevron_right_rounded, size: 18, color: OmiColors.textDisabled)
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
    final divided = DecoratedBox(
      decoration: BoxDecoration(border: Border(top: BorderSide(color: OmiColors.surface2))),
      child: row,
    );
    if (!elsewhere) return divided;
    return InkWell(
      key: ValueKey('episode_moment_${moment.id}'),
      onTap: () => onOpenConversation!(moment.conversationId),
      child: divided,
    );
  }
}
