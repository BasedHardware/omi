import 'package:flutter/material.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class EpisodeSectionTitle extends StatelessWidget {
  const EpisodeSectionTitle(this.title, {super.key, this.count});

  final String title;
  final int? count;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.lg, 0, OmiSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Text.rich(
              TextSpan(
                text: title,
                style: OmiType.headline,
                children: [
                  if (count != null)
                    TextSpan(
                      text: '  $count',
                      style: OmiType.headline.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w400),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class EpisodeContentCard extends StatelessWidget {
  const EpisodeContentCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Container(height: 1, color: OmiColors.surface2));
      rows.add(children[i]);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows),
    );
  }
}

class EpisodeBullets extends StatelessWidget {
  const EpisodeBullets(this.bullets, {super.key});

  final List<String> bullets;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final bullet in bullets)
          Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('•  ', style: OmiType.callout.copyWith(color: OmiColors.textTertiary, height: 1.4)),
                Expanded(child: Text(bullet, style: OmiType.callout.copyWith(height: 1.4))),
              ],
            ),
          ),
      ],
    );
  }
}

/// A card's title with something small at its trailing edge; the two stack when a large text

class EpisodeItemRow extends StatelessWidget {
  const EpisodeItemRow({super.key, required this.item, required this.now, this.onDismiss});

  final EpisodeItem item;
  final DateTime now;
  final ValueChanged<EpisodeItem>? onDismiss;

  @override
  Widget build(BuildContext context) {
    final saved = item.status == EpisodeItemStatus.kept;
    final fresh = now.difference(item.createdAt).inMinutes < 2;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 48),
      child: Row(
        children: [
          Icon(
            saved ? Icons.check_circle_rounded : (item.isReminder ? Icons.alarm_rounded : Icons.radio_button_unchecked),
            size: 22,
            color: saved ? OmiColors.textPrimary : OmiColors.textTertiary,
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(child: Text(item.text, style: OmiType.callout)),
          const SizedBox(width: OmiSpacing.xs),
          Text(
            fresh ? context.l10n.episodeNow : OmiDateFormat.of(context).time(item.createdAt),
            style: OmiType.footnote.copyWith(color: fresh ? OmiColors.success : OmiColors.textTertiary),
          ),
          if (!saved && onDismiss != null)
            OmiIconButton(
              key: ValueKey('episode_item_dismiss_${item.id}'),
              icon: Icon(Icons.close_rounded, size: 18, color: OmiColors.textTertiary),
              label: context.l10n.undo,
              onPressed: () => onDismiss!(item),
            ),
        ],
      ),
    );
  }
}

class EpisodeMomentRow extends StatelessWidget {
  const EpisodeMomentRow({super.key, required this.moment, required this.current});

  final EpisodeMoment moment;
  final bool current;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final when = current ? l10n.episodeNow : OmiDateFormat.of(context).time(moment.startedAt);
    final tint = current ? OmiColors.success : OmiColors.textTertiary;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 46),
      child: Row(
        children: [
          SizedBox(
            width: 64,
            child: Text(when, style: OmiType.footnote.copyWith(color: tint)),
          ),
          Expanded(child: Text(moment.heading.isEmpty ? '—' : moment.heading, style: OmiType.callout)),
          Text(EpisodePresentation.runningLength(moment.duration, l10n), style: OmiType.footnote.copyWith(color: tint)),
        ],
      ),
    );
  }
}
