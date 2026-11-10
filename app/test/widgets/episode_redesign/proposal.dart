import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_content.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Review-only composition. Never imported by app/lib. English proposal copy stays here
/// until David approves the render; shipping copy must use the l10n tool.
class EpisodeRedesignProposal extends StatefulWidget {
  const EpisodeRedesignProposal({super.key, required this.episode});
  final Episode episode;

  @override
  State<EpisodeRedesignProposal> createState() => _EpisodeRedesignProposalState();
}

class _EpisodeRedesignProposalState extends State<EpisodeRedesignProposal> {
  bool fullSummary = false;
  bool showMore = false;

  @override
  Widget build(BuildContext context) {
    final episode = widget.episode;
    final dates = OmiDateFormat.of(context);
    final members = episode.members.where((m) => !m.isHiddenFromDefaultList).toList();
    // Reuse the existing authoritative signal. Unknown/legacy rows stay visible.
    final quiet = members.where((m) => m.homeStep == 'noise').toList();
    final main = members.where((m) => m.homeStep != 'noise').toList();
    final moments = episode.moments.where((m) => m.points.isNotEmpty).toList();
    final shown = fullSummary ? moments : moments.take(2);
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        leading: const OmiBackButton(),
        actions: [
          OmiIconButton.filled(icon: const Icon(Icons.more_vert, size: 16), label: 'More options', onPressed: () {}),
        ],
      ),
      body: ListView(
        key: const Key('proposal_scroll'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xl),
        children: [
          Text(episode.title, style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4)),
          const SizedBox(height: OmiSpacing.sm),
          Text(
              '${dates.weekdayDate(episode.startedAt)} · ${dates.timeRange(episode.startedAt, episode.lastActivityAt)}',
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(height: OmiSpacing.lg),
          Container(
            padding: const EdgeInsets.all(OmiSpacing.md),
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Summary', style: OmiType.title3),
                const SizedBox(height: OmiSpacing.sm),
                Text(episode.lede, style: OmiType.callout.copyWith(height: 1.45)),
                for (final moment in shown) ...[
                  const SizedBox(height: OmiSpacing.lg),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: Text(moment.heading, style: OmiType.headline)),
                      const SizedBox(width: OmiSpacing.sm),
                      Text(dates.time(moment.startedAt),
                          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, height: 1.5)),
                    ],
                  ),
                  for (final point in moment.points) ...[
                    const SizedBox(height: OmiSpacing.sm),
                    Text(point.text, style: OmiType.callout.copyWith(height: 1.4)),
                    for (final detail in point.details)
                      Padding(
                        padding: const EdgeInsets.only(top: OmiSpacing.xs, left: OmiSpacing.sm),
                        child:
                            Text(detail, style: OmiType.subhead.copyWith(height: 1.4, color: OmiColors.textSecondary)),
                      ),
                  ],
                ],
                if (moments.length > 2)
                  Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: OmiButton.tertiary(
                      key: const Key('full_summary_toggle'),
                      label: fullSummary ? 'Show Less Summary' : 'Read Full Summary',
                      size: OmiButtonSize.compact,
                      icon: fullSummary ? Icons.expand_less : Icons.expand_more,
                      onPressed: () => setState(() => fullSummary = !fullSummary),
                    ),
                  ),
                if (episode.followUps.isNotEmpty) ...[
                  const SizedBox(height: OmiSpacing.md),
                  Divider(color: OmiColors.border, height: 1),
                  const SizedBox(height: OmiSpacing.md),
                  Text(context.l10n.episodeFollowUps, style: OmiType.headline),
                  const SizedBox(height: OmiSpacing.sm),
                  EpisodeBullets(episode.followUps),
                ],
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.conversations, key: const Key('proposal_conversations'), style: OmiType.title3),
          const SizedBox(height: OmiSpacing.xs),
          for (final member in main) _CompactRow(member),
          if (quiet.isNotEmpty) ...[
            OmiButton.tertiary(
              key: const Key('noise_toggle'),
              label: showMore ? 'Hide Extra Recordings' : 'Show ${quiet.length} More Recordings',
              icon: showMore ? Icons.expand_less : Icons.expand_more,
              size: OmiButtonSize.compact,
              onPressed: () => setState(() => showMore = !showMore),
            ),
            if (showMore) ...[for (final member in quiet) _CompactRow(member)],
          ],
        ],
      ),
    );
  }
}

class _CompactRow extends StatelessWidget {
  const _CompactRow(this.member);
  final ServerConversation member;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: InkWell(
        key: ValueKey('compact_${member.id}'),
        onTap: () {}, // Visual affordance only; real detail navigation follows render approval.
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
          decoration: BoxDecoration(border: Border(bottom: BorderSide(color: OmiColors.border, width: 0.5))),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 66,
                child: Text(OmiDateFormat.of(context).time(member.startedAt ?? member.createdAt),
                    style: OmiType.footnote.copyWith(height: 1.7, color: OmiColors.textTertiary)),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(member.structured.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: OmiType.body),
                    const SizedBox(height: OmiSpacing.xxs),
                    if (member.structured.overview.isNotEmpty)
                      Text(member.structured.overview,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ],
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              Icon(Icons.chevron_right, size: 18, color: OmiColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}
