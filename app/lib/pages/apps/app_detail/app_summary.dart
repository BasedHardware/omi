import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The top of an app's page (v2 `AppDetail`): its name large and who made it, with the check for
/// Omi's own apps. The icon sits beside it; ratings and users are [AppDetailStats] underneath.
class AppDetailHeader extends StatelessWidget {
  const AppDetailHeader({super.key, required this.name, required this.author, required this.official});

  final String name;
  final String author;
  final bool official;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          header: true,
          child: Text(
            name,
            style: OmiType.title2.copyWith(fontWeight: FontWeight.w700),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(height: 2),
        Row(
          children: [
            Flexible(
              child: Text(
                author,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (official) ...[
              const SizedBox(width: OmiSpacing.xxs),
              FaIcon(FontAwesomeIcons.solidCircleCheck, size: 13, color: OmiColors.textSecondary),
            ],
          ],
        ),
      ],
    );
  }
}

/// Ratings, users and (for an integration) what sets it off, as three columns between hairlines
/// (v2 `AppDetail`: "26 RATINGS 3.3 out of 5 · USERS 45.6K · TRIGGER End of conversation").
/// Columns without data are left out; with none, nothing is drawn.
class AppDetailStats extends StatelessWidget {
  const AppDetailStats({
    super.key,
    required this.ratingCount,
    required this.rating,
    required this.installs,
    this.trigger,
    this.onRatingTap,
  });

  final int ratingCount;
  final String? rating;
  final int installs;

  /// What makes the app run ("Conversation Creation"); null for apps that are not integrations.
  final String? trigger;

  /// Scrolls to the reviews.
  final VoidCallback? onRatingTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final columns = <Widget>[
      if (ratingCount > 0)
        _AppStat(
          key: const Key('app_stat_ratings'),
          label: l10n.ratingsCount(NumberFormat.decimalPattern(l10n.localeName).format(ratingCount)),
          value: rating ?? '',
          caption: l10n.appOutOfFive,
          onTap: onRatingTap,
        ),
      if (installs > 0)
        _AppStat(
          key: const Key('app_stat_users'),
          label: l10n.appStatUsers,
          value: NumberFormat.compact(locale: l10n.localeName).format(installs),
        ),
      if (trigger != null)
        _AppStat(key: const Key('app_stat_trigger'), label: l10n.permissionTypeTrigger, value: trigger!),
    ];
    if (columns.isEmpty) return const SizedBox.shrink();
    final hairline = BorderSide(color: OmiColors.border, width: 0.5);
    return DecoratedBox(
      decoration: BoxDecoration(border: Border(top: hairline, bottom: hairline)),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = 0; i < columns.length; i++) ...[
              if (i > 0) VerticalDivider(width: 1, thickness: 0.5, color: OmiColors.border),
              Expanded(child: columns[i]),
            ],
          ],
        ),
      ),
    );
  }
}

class _AppStat extends StatelessWidget {
  const _AppStat({super.key, required this.label, required this.value, this.caption, this.onTap});

  final String label;
  final String value;
  final String? caption;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final column = Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs, vertical: OmiSpacing.xs),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label.toUpperCase(),
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: OmiType.caption.copyWith(
              color: OmiColors.textTertiary,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: OmiType.headline.copyWith(fontWeight: FontWeight.w700),
          ),
          if (caption != null)
            Text(caption!, textAlign: TextAlign.center, style: OmiType.caption.copyWith(color: OmiColors.textTertiary)),
        ],
      ),
    );
    if (onTap == null) return MergeSemantics(child: column);
    return MergeSemantics(
      child: Semantics(
          button: true, child: GestureDetector(onTap: onTap, behavior: HitTestBehavior.opaque, child: column)),
    );
  }
}
