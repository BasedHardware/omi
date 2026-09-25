import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AppDetailSummary extends StatelessWidget {
  final String name;
  final String author;
  final bool official;
  final int ratingCount;
  final String? rating;
  final int installs;
  final VoidCallback? onRatingTap;
  final Widget action;

  const AppDetailSummary({
    super.key,
    required this.name,
    required this.author,
    required this.official,
    required this.ratingCount,
    required this.rating,
    required this.installs,
    required this.action,
    this.onRatingTap,
  });

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 108),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name,
                style: OmiType.title3,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: OmiSpacing.xxs),
              Row(
                children: [
                  Flexible(
                    child: Text(
                      author,
                      style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (official) ...[
                    const SizedBox(width: OmiSpacing.xxs),
                    const FaIcon(FontAwesomeIcons.solidCircleCheck, size: 14, color: OmiColors.textPrimary),
                  ],
                ],
              ),
              const SizedBox(height: OmiSpacing.xs),
              GestureDetector(
                onTap: onRatingTap,
                child: Row(
                  children: [
                    if (ratingCount > 0) ...[
                      const FaIcon(FontAwesomeIcons.solidStar, size: 11, color: OmiColors.textPrimary),
                      const SizedBox(width: OmiSpacing.xxs),
                      Text(
                        '$rating ($ratingCount)',
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                      if (installs > 0) Text('  ·  ', style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                    ],
                    if (installs > 0)
                      Text(
                        context.l10n.appUsersCount((installs / 10).round() * 10),
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      ),
                  ],
                ),
              ),
            ],
          ),
          action,
        ],
      ),
    );
  }
}
