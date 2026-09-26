import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'app_detail/app_detail.dart';

class AppListItem extends StatelessWidget {
  final App app;
  final int index;
  final bool showPrivateIcon;

  const AppListItem({super.key, required this.app, required this.index, this.showPrivateIcon = true});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _openDetail(context),
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: EdgeInsets.only(bottom: 8, top: index == 0 ? 16 : 0),
        decoration: BoxDecoration(
          color: OmiColors.surface1.withValues(alpha: 0.3),
          borderRadius: OmiRadius.mdAll,
        ),
        child: Row(
          children: [
            // App icon
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
                  errorWidget: (context, url, error) => const Icon(Icons.apps, size: 30, color: OmiColors.textTertiary),
                ),
              ),
            ),

            const SizedBox(width: 16),

            // App details
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    app.name.decodeString + (app.private && showPrivateIcon ? " 🔒".decodeString : ''),
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
                          style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textSecondary),
                        ),
                        const SizedBox(width: 4),
                        Text('(${app.ratingCount})', style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                      ],
                    ),
                  ],
                ],
              ),
            ),

            const SizedBox(width: 12),

            // Action button
            AppListActionButton(app: app, loadingIndex: index, onOpen: () => _openDetail(context)),
          ],
        ),
      ),
    );
  }

  Future<void> _openDetail(BuildContext context) async {
    PlatformManager.instance.analytics.pageOpened('App Detail');
    await routeToPage(context, AppDetailPage(app: app));
  }
}
