import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Placeholder rows shown while an app search is running.
///
/// Extracted from `ExploreInstallPage` so the loading state can be pumped on its
/// own in a widget test — a search that outlives the shimmer animation is the
/// case that matters here, and it is not reachable through the full page without
/// a live backend.
class SearchLoadingSliver extends StatelessWidget {
  /// Creates the loading placeholder shown during a search.
  const SearchLoadingSliver({super.key, this.placeholderCount = 5});

  /// How many placeholder rows to draw.
  final int placeholderCount;

  @override
  Widget build(BuildContext context) {
    return SliverPadding(
      padding: const EdgeInsets.only(bottom: 64, left: 20, right: 20, top: 20),
      sliver: SliverMainAxisGroup(
        slivers: [
          const SliverToBoxAdapter(child: _SearchProgressBar()),
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (context, index) => const _ShimmerListItem(),
              childCount: placeholderCount,
            ),
          ),
        ],
      ),
    );
  }
}

/// The one thing on screen that keeps moving for as long as the search runs.
///
/// The shimmer placeholders below it stop animating after five seconds and go
/// static, so on a slow search they stop being evidence of anything. This does
/// not time out, which is the whole point: it separates "still working" from
/// "wedged" at the moment the user starts to wonder.
class _SearchProgressBar extends StatelessWidget {
  const _SearchProgressBar();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(bottom: OmiSpacing.md),
      child: LinearProgressIndicator(
        // Indeterminate: a search has no known duration, and a determinate bar
        // would have to invent a percentage that then appears to stall.
        minHeight: 3,
        backgroundColor: OmiColors.surface1,
        valueColor: AlwaysStoppedAnimation<Color>(OmiColors.textPrimary),
        borderRadius: OmiRadius.smAll,
      ),
    );
  }
}

class _ShimmerListItem extends StatelessWidget {
  const _ShimmerListItem();

  @override
  Widget build(BuildContext context) {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface2,
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.md),
        margin: const EdgeInsets.only(bottom: OmiSpacing.xs),
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Row(
          children: [
            Container(
              width: 60,
              height: 60,
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            ),
            const SizedBox(width: OmiSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    height: 18,
                    decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  Container(
                    width: 150,
                    height: 14,
                    decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                  ),
                ],
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Container(
              width: 72,
              height: 32,
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
            ),
          ],
        ),
      ),
    );
  }
}
