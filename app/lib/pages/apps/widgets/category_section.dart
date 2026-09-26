import 'dart:math';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/ui/ui.dart';

class CategorySection extends StatelessWidget {
  final String categoryName;
  final List<App> apps;
  final VoidCallback onViewAll;
  final bool showViewAll;

  const CategorySection({
    super.key,
    required this.categoryName,
    required this.apps,
    required this.onViewAll,
    this.showViewAll = true,
  });

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) {
      return const SizedBox.shrink();
    }

    // Apps are already sorted by score on the backend, just take first 9
    final displayedApps = apps.take(9).toList();

    // --- Configuration Constants ---
    // Heights follow the reader's text size: fixed 85 / 60 pt rows cut the app's name, category
    // and rating (and the section title) at a larger text size (layout lint, 1.3x).
    final scaler = MediaQuery.textScalerOf(context);
    final direction = Directionality.of(context);
    double lineOf(TextStyle style) {
      final painter =
          TextPainter(text: TextSpan(text: 'Ag', style: style), textScaler: scaler, textDirection: direction)..layout();
      final height = painter.height;
      painter.dispose();
      return height;
    }

    final rowText = lineOf(OmiType.body) + 2 + lineOf(OmiType.footnote) + 2 + lineOf(OmiType.caption);
    final double targetItemHeight = max(85.0, 16 + max(52.0, rowText) + 1);
    const double crossAxisSpacing = 0.0;
    const double mainAxisSpacing = 14.0;
    const int maxRows = 3;
    final double titleSectionHeight = max(60.0, 24 + 16 + lineOf(OmiType.title2));

    // --- Dynamic Calculation ---
    final int numRows = min(maxRows, displayedApps.length);
    if (numRows == 0) return const SizedBox.shrink();

    final double gridContentHeight = numRows * targetItemHeight + max(0, numRows - 1) * crossAxisSpacing;
    final double totalSectionHeight = titleSectionHeight + gridContentHeight;

    // Cards keep their width (85 / 0.28 pt) as rows grow taller with the text.
    final double childAspectRatio = targetItemHeight / (85.0 / 0.28);

    return Container(
      height: totalSectionHeight,
      margin: const EdgeInsets.only(top: 0, bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Section header
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
            child: Row(
              children: [
                Text(
                  categoryName,
                  style: OmiType.title2,
                ),
                const Spacer(),
                if (showViewAll)
                  GestureDetector(
                    onTap: onViewAll,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.tileAll),
                          child: Text(
                            context.l10n.all,
                            style:
                                OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                          ),
                        ),
                        // const SizedBox(width: 8),
                        Icon(Icons.chevron_right_rounded, color: OmiColors.textTertiary, size: 18),
                      ],
                    ),
                  ),
              ],
            ),
          ),

          // Horizontal scrolling grid of apps
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 0, 0),
              child: GridView.builder(
                scrollDirection: Axis.horizontal,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: numRows,
                  childAspectRatio: childAspectRatio,
                  crossAxisSpacing: crossAxisSpacing,
                  mainAxisSpacing: mainAxisSpacing,
                ),
                itemCount: displayedApps.length,
                itemBuilder: (context, index) => SectionAppItemCard(app: displayedApps[index], index: index),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class SectionAppItemCard extends StatelessWidget {
  final App app;
  final int index;

  const SectionAppItemCard({super.key, required this.app, required this.index});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _openDetail(context),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 4.0),
        decoration: const BoxDecoration(borderRadius: OmiRadius.mdAll),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            CachedNetworkImage(
              imageUrl: app.getImageUrl(),
              httpHeaders: const {
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
              },
              imageBuilder: (context, imageProvider) => Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  shape: BoxShape.rectangle,
                  borderRadius: OmiRadius.tileAll,
                  image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                ),
              ),
              placeholder: (context, url) => Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.tileAll),
              ),
              errorWidget: (context, url, error) => Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.tileAll),
                child: Icon(Icons.error_outline, color: OmiColors.textTertiary, size: 24),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    app.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(top: 2.0),
                    child: Builder(
                      builder: (context) {
                        // Look up category title from backend-provided categories
                        final categories = context.read<AddAppProvider>().categories;
                        final category = categories.firstWhere(
                          (c) => c.id == app.category,
                          orElse: () => Category(id: app.category, title: app.getCategoryName()),
                        );
                        return Text(
                          category.getLocalizedTitle(context),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                        );
                      },
                    ),
                  ),
                  if (app.ratingAvg != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      '${app.getRatingAvg()!} · ${context.l10n.appRatingCount(app.ratingCount)}',
                      style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 8),
            AppListActionButton(app: app, onOpen: () => _openDetail(context)),
          ],
        ),
      ),
    );
  }

  Future<void> _openDetail(BuildContext context) async {
    PlatformManager.instance.analytics.pageOpened('App Detail');
    await routeToPage(context, AppDetailPage(app: app));
    if (context.mounted) {
      context.read<AppProvider>().filterApps();
    }
  }
}
