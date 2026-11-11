// Full composed episode notes and follow-ups, expanded at page open.
// Reuses moment transcript navigation and the canonical task creation path.

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_content.dart';
import 'package:omi/pages/episodes/episode_follow_up.dart';
import 'package:omi/pages/episodes/episode_sections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// All composed notes are visible immediately, with no extra heading or collapse.
class EpisodeSummary extends StatelessWidget {
  const EpisodeSummary(
      {super.key,
      required this.episode,
      required this.moments,
      required this.conversationId,
      required this.onOpenMoment});
  final Episode episode;
  final List<EpisodeMoment> moments;
  final String? conversationId;
  final ValueChanged<EpisodeMoment> onOpenMoment;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('episode_summary'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (episode.lede.trim().isNotEmpty)
            Text(episode.lede, key: const Key('episode_lede'), style: OmiType.callout.copyWith(height: 1.45)),
          if (moments.any((m) => m.points.isNotEmpty))
            EpisodeSections(moments: moments, onOpenMoment: onOpenMoment)
          else
            EpisodeBullets(episode.bullets),
          if (episode.followUps.isNotEmpty) ...[
            const SizedBox(height: OmiSpacing.md),
            Divider(color: OmiColors.border, height: 1),
            const SizedBox(height: OmiSpacing.md),
            Text(context.l10n.episodeFollowUps, style: OmiType.headline),
            const SizedBox(height: OmiSpacing.xs),
            // Composer follow-ups are episode-level text without per-item source ids.
            // Link to the first retained conversation; do not infer a precise source span.
            for (final text in episode.followUps.where((text) => text.trim().isNotEmpty).toSet())
              EpisodeFollowUp(
                key: ValueKey('${episode.id}:$text'),
                episodeId: episode.id,
                text: text,
                conversationId: conversationId,
              ),
          ],
        ],
      ),
    );
  }
}
