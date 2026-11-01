import 'package:flutter/material.dart';

import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A composed episode's body: each moment is a section with its points, the way a conversation's
/// summary reads. [onOpenMoment] opens the moment in its conversation's transcript.
class EpisodeSections extends StatelessWidget {
  const EpisodeSections({super.key, required this.moments, this.onOpenMoment});

  final List<EpisodeMoment> moments;
  final ValueChanged<EpisodeMoment>? onOpenMoment;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final moment in moments)
          if (moment.points.isNotEmpty) EpisodeSection(moment: moment, onOpen: onOpenMoment),
      ],
    );
  }
}

class EpisodeSection extends StatelessWidget {
  const EpisodeSection({super.key, required this.moment, this.onOpen});

  final EpisodeMoment moment;
  final ValueChanged<EpisodeMoment>? onOpen;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final when =
        '${OmiDateFormat.of(context).time(moment.startedAt)} · ${EpisodePresentation.runningLength(moment.duration, l10n)}';
    return Padding(
      key: ValueKey('episode_section_${moment.id}'),
      padding: const EdgeInsets.only(top: OmiSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(moment.heading, style: OmiType.headline),
                    const SizedBox(height: 2),
                    Text(when, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              if (onOpen != null)
                OmiIconButton(
                  key: ValueKey('episode_section_open_${moment.id}'),
                  icon: Icon(Icons.graphic_eq_rounded, size: 20, color: OmiColors.textTertiary),
                  label: l10n.episodeOpenTranscript,
                  onPressed: () => onOpen!(moment),
                ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xs),
          for (final point in moment.points) _Point(point),
        ],
      ),
    );
  }
}

class _Point extends StatelessWidget {
  const _Point(this.point);

  final EpisodePoint point;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _BulletLine(point.text, indent: 0),
          for (final detail in point.details) _BulletLine(detail, indent: OmiSpacing.lg, secondary: true),
        ],
      ),
    );
  }
}

class _BulletLine extends StatelessWidget {
  const _BulletLine(this.text, {required this.indent, this.secondary = false});

  final String text;
  final double indent;
  final bool secondary;

  @override
  Widget build(BuildContext context) {
    final style = OmiType.callout.copyWith(height: 1.4, color: secondary ? OmiColors.textSecondary : null);
    return Padding(
      padding: EdgeInsets.only(left: indent, bottom: OmiSpacing.xxs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(secondary ? '◦  ' : '•  ', style: style.copyWith(color: OmiColors.textTertiary)),
          Expanded(child: Text(text, style: style)),
        ],
      ),
    );
  }
}
