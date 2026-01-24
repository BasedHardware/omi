import 'dart:math';

import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';

/// A category section widget with unlimited horizontal scrolling for capability pages.
/// Unlike CategorySection which shows max 9 items, this shows all apps in the category.
class CapabilityCategorySection extends StatelessWidget {
  final String categoryName;
  final List<App> apps;

  // Layout constants
  static const double _targetItemHeight = 85.0;
  static const double _crossAxisSpacing = 0.0;
  static const double _mainAxisSpacing = 14.0;
  static const int _maxRows = 3;
  static const double _titleSectionHeight = 60.0;
  static const double _childAspectRatio = 0.28;

  const CapabilityCategorySection({
    super.key,
    required this.categoryName,
    required this.apps,
  });

  /// Look up category title from backend-provided categories.
  String _getCategoryTitle(BuildContext context, App app) {
    final categories = context.read<AddAppProvider>().categories;
    final category = categories.firstWhere(
      (c) => c.id == app.category,
      orElse: () => Category(id: app.category, title: app.getCategoryName()),
    );
    return category.title;
  }

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) {
      return const SizedBox.shrink();
    }

    final int numRows = min(_maxRows, apps.length);
    if (numRows == 0) return const SizedBox.shrink();

    final double gridContentHeight = numRows * _targetItemHeight + max(0, numRows - 1) * _crossAxisSpacing;
    final double totalSectionHeight = _titleSectionHeight + gridContentHeight;

    // Pre-compute category titles for all apps to avoid lookups during scroll
    final categoryTitles = {for (final app in apps) app.id: _getCategoryTitle(context, app)};

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
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade700,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${apps.length}',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade300,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Horizontal scrolling grid of apps - unlimited items
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 0, 0),
              child: GridView.builder(
                scrollDirection: Axis.horizontal,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: numRows,
                  childAspectRatio: _childAspectRatio,
                  crossAxisSpacing: _crossAxisSpacing,
                  mainAxisSpacing: _mainAxisSpacing,
                ),
                itemCount: apps.length,
                itemBuilder: (context, index) {
                  final app = apps[index];
                  return CapabilitySectionAppItemCard(
                    app: app,
                    categoryTitle: categoryTitles[app.id] ?? app.getCategoryName(),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class CapabilitySectionAppItemCard extends StatelessWidget {
  final App app;
  final String categoryTitle;

  const CapabilitySectionAppItemCard({
    super.key,
    required this.app,
    required this.categoryTitle,
  });

  @override
  Widget build(BuildContext context) {
    // Use Selector instead of Consumer to only rebuild when this specific app's enabled state changes
    return Selector<AppProvider, bool>(
      selector: (context, provider) {
        // Only select the enabled state of this specific app
        final currentApp = provider.apps.firstWhere(
          (a) => a.id == app.id,
          orElse: () => app,
        );
        return currentApp.enabled;
      },
      builder: (context, isEnabled, child) {
        return GestureDetector(
          onTap: () async {
            MixpanelManager().pageOpened('App Detail');
            await routeToPage(context, AppDetailPage(app: app));
            context.read<AppProvider>().filterApps();
          },
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 4.0),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12.0),
            ),
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
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      shape: BoxShape.rectangle,
                      borderRadius: BorderRadius.circular(8),
                      image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                    ),
                  ),
                  placeholder: (context, url) => Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      color: const Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  errorWidget: (context, url, error) => Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      color: const Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.error_outline, color: Colors.white54, size: 24),
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
                        style: const TextStyle(fontWeight: FontWeight.w500, color: Colors.white, fontSize: 17),
                      ),
                      Padding(
                        padding: const EdgeInsets.only(top: 2.0),
                        child: Text(
                          categoryTitle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.grey, fontSize: 13),
                        ),
                      ),
                      if (app.ratingAvg != null) ...[
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            const FaIcon(
                              FontAwesomeIcons.solidStar,
                              color: Color(0xFF8B5CF6),
                              size: 9,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              app.getRatingAvg()!,
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                                color: Colors.grey.shade300,
                              ),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              '(${app.ratingCount})',
                              style: TextStyle(
                                fontSize: 11,
                                color: Colors.grey.shade500,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),

                const SizedBox(width: 8),

                // Action button - Apple style
                Container(
                  width: 60,
                  height: 28,
                  decoration: BoxDecoration(
                    color: isEnabled ? Colors.grey.shade700 : Colors.white,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Center(
                    child: Text(
                      isEnabled ? 'Open' : 'Install',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: isEnabled ? Colors.white : Colors.black,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
