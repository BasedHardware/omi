import 'package:flutter/material.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/redesign/app_row_card.dart';
import 'package:omi/pages/apps/widgets/redesign/section_header.dart';

/// One section in the Apps listing.
///
/// Header on top, vertical list of borderless [AppRowCard]s underneath, each
/// separated by a hairline divider that's indented to align with the start of
/// the row's text (Things 3 / iOS Settings convention). No card backgrounds,
/// no carousel, no horizontal scroll.
class AppSection extends StatelessWidget {
  final String title;
  final List<App> apps;
  final int previewCount;
  final VoidCallback? onViewAll;

  const AppSection({
    super.key,
    required this.title,
    required this.apps,
    this.previewCount = 5,
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
        SectionHeader(title: title, onViewAll: showViewAll ? onViewAll : null),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              for (var i = 0; i < visible.length; i++) ...[
                AppRowCard(app: visible[i]),
                if (i != visible.length - 1) const _Divider(),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) {
    // Indent the hairline to start at the row's text column (icon width 56 +
    // gap 14 = 70). This is the iOS Settings / Things 3 convention.
    return Padding(
      padding: const EdgeInsets.only(left: 70),
      child: Container(
        height: 0.5,
        color: Colors.white.withValues(alpha: 0.06),
      ),
    );
  }
}
