import 'package:flutter/material.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one-line question for [item], worded on the client so it follows the app language.
String reviewQuestion(BuildContext context, ReviewItem item) {
  final l10n = context.l10n;
  return switch (item.kind) {
    ReviewItemKind.speaker => l10n.reviewQuestionSpeaker,
    ReviewItemKind.task => item.task!.description,
    ReviewItemKind.samePerson => l10n.reviewQuestionSamePerson(item.samePerson!.right.name),
    ReviewItemKind.spelling => l10n.reviewQuestionSpelling,
  };
}

IconData reviewKindIcon(ReviewItemKind kind) => switch (kind) {
      ReviewItemKind.speaker => Icons.record_voice_over_outlined,
      ReviewItemKind.task => Icons.task_alt,
      ReviewItemKind.samePerson => Icons.people_outline,
      ReviewItemKind.spelling => Icons.spellcheck,
    };

/// A 40pt circle holding a kind's icon, used where a card has no play button.
class ReviewKindBadge extends StatelessWidget {
  const ReviewKindBadge({super.key, required this.kind, this.size = 40});

  final ReviewItemKind kind;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
      child: Icon(reviewKindIcon(kind), size: 20, color: OmiColors.textPrimary),
    );
  }
}

/// The white play / stop circle that plays a speaker clip in place.
class ReviewPlayButton extends StatelessWidget {
  const ReviewPlayButton({super.key, required this.playing, required this.onPressed, this.size = 44});

  final bool playing;
  final VoidCallback onPressed;
  final double size;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      button: true,
      label: playing ? l10n.reviewStopClip : l10n.reviewPlayClip,
      child: Material(
        color: OmiColors.accent,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onPressed,
          child: SizedBox(
            width: size,
            height: size,
            child: Icon(playing ? Icons.stop_rounded : Icons.play_arrow_rounded, color: OmiColors.onAccent, size: 26),
          ),
        ),
      ),
    );
  }
}

/// A quick-answer capsule on a card (44pt tall). [primary] fills it with the accent.
class ReviewAnswerPill extends StatelessWidget {
  const ReviewAnswerPill({super.key, required this.label, required this.onPressed, this.primary = false});

  final String label;
  final VoidCallback? onPressed;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final background = primary ? OmiColors.accent : OmiColors.surface2;
    final foreground = primary ? OmiColors.onAccent : OmiColors.textPrimary;
    return Material(
      color: background,
      shape: const StadiumBorder(),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onPressed,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44, minWidth: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18),
            child: Center(
              widthFactor: 1,
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.subhead
                    .copyWith(color: foreground, fontWeight: primary ? FontWeight.w600 : FontWeight.w500),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A small tappable chip that leads to a person, organization, project or conversation.
class ReviewLinkChip extends StatelessWidget {
  const ReviewLinkChip({super.key, required this.label, required this.icon, this.onTap});

  final String label;
  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: OmiColors.sourceBadgeSurface,
      borderRadius: OmiRadius.smAll,
      child: InkWell(
        borderRadius: OmiRadius.smAll,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 32),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 14, color: onTap == null ? OmiColors.textSecondary : OmiColors.textPrimary),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.footnote.copyWith(
                      fontWeight: FontWeight.w500,
                      color: onTap == null ? OmiColors.textSecondary : OmiColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

IconData entityIcon(EntityType type) => switch (type) {
      EntityType.person => Icons.person_outline,
      EntityType.organization => Icons.apartment_outlined,
      EntityType.project => Icons.folder_outlined,
    };

/// An initial avatar: a circle for a person, a rounded square for an organization.
class EntityInitialAvatar extends StatelessWidget {
  const EntityInitialAvatar({super.key, required this.name, required this.type, this.size = 28});

  final String name;
  final EntityType type;
  final double size;

  @override
  Widget build(BuildContext context) {
    final trimmed = name.trim();
    final initial = trimmed.isEmpty ? '?' : trimmed.characters.first.toUpperCase();
    if (type == EntityType.project) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: BorderRadius.circular(size / 4)),
        child: Icon(Icons.folder_outlined, size: size * 0.5, color: OmiColors.textPrimary),
      );
    }
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: OmiColors.surface3,
        shape: type == EntityType.person ? BoxShape.circle : BoxShape.rectangle,
        borderRadius: type == EntityType.person ? null : BorderRadius.circular(size / 4),
      ),
      child: Text(initial, style: OmiType.footnote.copyWith(fontSize: size * 0.42, fontWeight: FontWeight.w600)),
    );
  }
}

/// A grey upper-case section label above a group on a page.
class ReviewSectionLabel extends StatelessWidget {
  const ReviewSectionLabel({super.key, required this.label, this.trailing});

  final String label;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.xxs, OmiSpacing.xxs),
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              header: true,
              child: Text(
                label.toUpperCase(),
                style: OmiType.footnote.copyWith(
                  fontWeight: FontWeight.w600,
                  color: OmiColors.textSecondary,
                  letterSpacing: 0.4,
                ),
              ),
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
