import 'package:flutter/material.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/redesign/app_row_card.dart';
import 'package:omi/pages/apps/widgets/redesign/section_header.dart';

/// One section in the Apps listing — header + vertical list of [AppRowCard].
///
/// Replaces the horizontal-scrolling icon-grid carousel (`CategorySection`).
/// The vertical-list shape is the single biggest visual differentiator from
/// the iOS App Store.
class AppSection extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<App> apps;
  final int previewCount;
  final VoidCallback? onViewAll;

  const AppSection({
    super.key,
    required this.title,
    required this.apps,
    this.subtitle,
    this.previewCount = 4,
    this.onViewAll,
  });

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) return const SizedBox.shrink();
    final visible = apps.take(previewCount).toList();
    final showViewAll = onViewAll != null && apps.length > previewCount;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          title: title,
          subtitle: subtitle,
          onViewAll: showViewAll ? onViewAll : null,
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            children: [
              for (var i = 0; i < visible.length; i++) ...[
                AppRowCard(app: visible[i]),
                if (i != visible.length - 1) const SizedBox(height: 8),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
