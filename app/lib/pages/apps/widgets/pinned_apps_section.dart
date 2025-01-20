import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/app_detail/app_detail.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class PinnedAppsSection extends StatelessWidget {
  final List<App> apps;
  const PinnedAppsSection({super.key, required this.apps});

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) {
      return const SizedBox.shrink();
    }

    // Take only first 4 apps
    final displayApps = apps.take(4).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8.0, vertical: 12.0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 6.0),
            child: Text('Pinned Apps', style: const TextStyle(color: Colors.white, fontSize: 18)),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: displayApps.map((app) => PinnedAppCard(app: app)).toList(),
          ),
        ],
      ),
    );
  }
}

class PinnedAppCard extends StatelessWidget {
  final App app;

  const PinnedAppCard({super.key, required this.app});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          MixpanelManager().pageOpened('App Detail From Pinned Apps');
          await routeToPage(context, AppDetailPage(app: app));
          provider.setApps();
        },
        child: Container(
          width: 80,
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: Colors.grey[900],
            borderRadius: BorderRadius.circular(10.0),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CachedNetworkImage(
                imageUrl: app.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: BorderRadius.circular(8),
                    image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                  ),
                ),
                placeholder: (context, url) => const SizedBox(
                  width: 48,
                  height: 48,
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                ),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              ),
              const SizedBox(height: 4),
              Text(
                app.name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                  fontSize: 11,
                ),
              ),
              if (app.ratingAvg != null) ...[
                const SizedBox(height: 2),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      app.getRatingAvg()!,
                      style: const TextStyle(fontSize: 10, color: Colors.deepPurple),
                    ),
                    const SizedBox(width: 1),
                    const Icon(Icons.star, color: Colors.deepPurple, size: 10),
                  ],
                ),
              ],
            ],
          ),
        ),
      );
    });
  }
}