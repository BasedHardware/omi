import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/ui/ui.dart';

// Custom notification class to communicate with parent widgets
class SelectAppNotification extends Notification {
  final App app;

  SelectAppNotification(this.app);
}

class PopularAppsSection extends StatelessWidget {
  final List<App> apps;

  const PopularAppsSection({super.key, required this.apps});

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) {
      return const SizedBox.shrink();
    }

    // Show top 9 popular apps
    final displayedApps = apps.take(9).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section header - Apple style
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: Row(
            children: [
              Text(
                context.l10n.popularApps,
                style: OmiType.title3,
              ),
              const Spacer(),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                    child: Text(
                      '${apps.length}',
                      style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Icon(Icons.chevron_right, color: Colors.grey.shade400, size: 16),
                ],
              ),
            ],
          ),
        ),

        // Apps list - Apple style
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 20),
          itemCount: displayedApps.length,
          separatorBuilder: (context, index) => const SizedBox(height: 12),
          itemBuilder: (context, index) {
            final app = displayedApps[index];
            void openApp() {
              final appProvider = context.read<AppProvider>();
              appProvider.filterApps();
              PlatformManager.instance.analytics.pageOpened('App Detail');
              // clear any existing search
              appProvider.searchApps('');
              SelectAppNotification(app).dispatch(context);
            }

            return GestureDetector(
              onTap: openApp,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: OmiColors.surface1.withValues(alpha: 0.3),
                  borderRadius: OmiRadius.mdAll,
                ),
                child: Row(
                  children: [
                    // App icon - Apple style square with rounded corners
                    ClipRRect(
                      borderRadius: OmiRadius.mdAll,
                      child: Container(
                        width: 60,
                        height: 60,
                        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                        child: CachedNetworkImage(
                          imageUrl: app.getImageUrl(),
                          httpHeaders: const {
                            "User-Agent":
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                          },
                          fit: BoxFit.cover,
                          placeholder: (context, url) => ShimmerWithTimeout(
                            baseColor: OmiColors.surface1,
                            highlightColor: OmiColors.surface2,
                            child: Container(
                              width: double.infinity,
                              height: double.infinity,
                              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
                            ),
                          ),
                          errorWidget: (context, url, error) =>
                              const Icon(Icons.apps, size: 30, color: OmiColors.textTertiary),
                        ),
                      ),
                    ),

                    const SizedBox(width: 16),

                    // App details - Apple style
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            app.name,
                            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            app.description,
                            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          if (app.ratingAvg != null) ...[
                            const SizedBox(height: 4),
                            Row(
                              children: [
                                const Icon(Icons.star_rounded, color: Colors.white, size: 14),
                                const SizedBox(width: 4),
                                Text(
                                  app.getRatingAvg()!,
                                  style: OmiType.footnote.copyWith(
                                    fontWeight: FontWeight.w500,
                                    color: OmiColors.textSecondary,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  '(${app.ratingCount})',
                                  style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),

                    const SizedBox(width: 12),

                    AppListActionButton(app: app, onOpen: openApp),
                  ],
                ),
              ),
            );
          },
        ),

        const SizedBox(height: 8),
      ],
    );
  }
}
