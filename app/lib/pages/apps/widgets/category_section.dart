import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'dart:math';

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

    // Sort apps by downloads (most downloaded first) and show max 9 apps
    final sortedApps = List<App>.from(apps);
    sortedApps.sort((a, b) => (b.installs ?? 0).compareTo(a.installs ?? 0));
    final displayedApps = sortedApps.take(9).toList();

    // --- Configuration Constants ---
    const double targetItemHeight = 85.0;
    const double crossAxisSpacing = 0.0;
    const double mainAxisSpacing = 14.0;
    const int maxRows = 3;
    const double titleSectionHeight = 60.0;

    // --- Dynamic Calculation ---
    final int numRows = min(maxRows, displayedApps.length);
    if (numRows == 0) return const SizedBox.shrink();

    final double gridContentHeight = numRows * targetItemHeight + max(0, numRows - 1) * crossAxisSpacing;
    final double totalSectionHeight = titleSectionHeight + gridContentHeight;

    const double childAspectRatio = 0.28;

    return Container(
      height: totalSectionHeight,
      margin: const EdgeInsets.only(top: 0, bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Section header - Apple style
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
                if (showViewAll)
                  GestureDetector(
                    onTap: onViewAll,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.grey.shade700,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            'All',
                            style: TextStyle(
                              fontSize: 11,
                              color: Colors.grey.shade300,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        // const SizedBox(width: 8),
                        Icon(
                          Icons.chevron_right,
                          color: Colors.grey.shade400,
                          size: 16,
                        ),
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
                itemBuilder: (context, index) => SectionAppItemCard(
                  app: displayedApps[index],
                  index: index,
                ),
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
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
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
                      color: Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  errorWidget: (context, url, error) => Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      color: Color(0xFF35343B),
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
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w500, color: Colors.white, fontSize: 17),
                      ),
                      Padding(
                        padding: const EdgeInsets.only(top: 2.0),
                        child: Text(
                          app.description.decodeString,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: Colors.grey, fontSize: 13),
                        ),
                      ),
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
