import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/widgets/redesign/status_pill.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

/// Vertical row card replacing the App-Store-style list item / icon-tile carousel cell.
///
/// Visual shape (Shopify App Store / GPT Store inspired):
/// - 48×48 icon (smaller than App Store's 60-64)
/// - bold name + 2-line description + author/status footer
/// - single purple ★ + score on the trailing edge (no 5-star row, no "(52)" parenthetical)
/// - no inline action button — entire row taps through to detail
class AppRowCard extends StatelessWidget {
  final App app;
  final bool showPrivateIcon;

  const AppRowCard({super.key, required this.app, this.showPrivateIcon = true});

  @override
  Widget build(BuildContext context) {
    return Selector<AppProvider, bool>(
      selector: (context, provider) {
        final current = provider.apps.firstWhere((a) => a.id == app.id, orElse: () => app);
        return current.enabled;
      },
      builder: (context, isEnabled, child) {
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () async {
            MixpanelManager().pageOpened('App Detail');
            await routeToPage(context, AppDetailPage(app: app));
            if (context.mounted) {
              context.read<AppProvider>().filterApps();
            }
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25).withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                _buildIcon(),
                const SizedBox(width: 12),
                Expanded(child: _buildBody(context, isEnabled)),
                const SizedBox(width: 8),
                _buildRating(),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildIcon() {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: const Color(0xFF35343B),
          borderRadius: BorderRadius.circular(12),
        ),
        child: CachedNetworkImage(
          imageUrl: app.getImageUrl(),
          httpHeaders: const {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
          },
          fit: BoxFit.cover,
          placeholder: (context, url) => ShimmerWithTimeout(
            baseColor: const Color(0xFF1F1F25),
            highlightColor: const Color(0xFF35343B),
            child: Container(color: const Color(0xFF1F1F25)),
          ),
          errorWidget: (context, url, error) => Icon(Icons.apps, size: 24, color: Colors.grey.shade600),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context, bool isEnabled) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          app.name.decodeString + (app.private && showPrivateIcon ? ' 🔒'.decodeString : ''),
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        if (app.description.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            app.description,
            style: TextStyle(fontSize: 13, color: Colors.grey.shade400, height: 1.3),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
        const SizedBox(height: 4),
        Row(
          children: [
            Flexible(
              child: Text(
                app.author.isNotEmpty ? 'By ${app.author}' : (app.email ?? ''),
                style: TextStyle(fontSize: 12, color: Colors.grey.shade500, fontWeight: FontWeight.w500),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (isEnabled) ...[
              const SizedBox(width: 8),
              const StatusPill(label: 'Connected', tone: StatusPillTone.success),
            ] else if (_needsSetup(app)) ...[
              const SizedBox(width: 8),
              const StatusPill(label: 'Setup needed', tone: StatusPillTone.warning),
            ],
          ],
        ),
      ],
    );
  }

  Widget _buildRating() {
    if (app.ratingAvg == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.star_rounded, color: Color(0xFF8B5CF6), size: 14),
              const SizedBox(width: 2),
              Text(
                app.getRatingAvg() ?? '',
                style: const TextStyle(fontSize: 13, color: Colors.white, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ],
      ),
    );
  }

  bool _needsSetup(App app) {
    // External integrations with auth steps that aren't completed yet need setup.
    // We can't reliably check setup completion from the row context, so this is a
    // conservative signal: only show the pill if the app is external and not yet enabled.
    return !app.enabled && app.worksExternally();
  }
}
