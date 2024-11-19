import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/app_detail/app_detail.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class AppSectionCard extends StatelessWidget {
  final String title;
  final List<App> apps;
  final double? height;
  const AppSectionCard({super.key, required this.title, required this.apps, this.height});

  @override
  Widget build(BuildContext context) {
    if (apps.isEmpty) {
      return const SizedBox.shrink();
    }
    return Container(
      padding: const EdgeInsets.only(top: 16.0, left: 10, right: 10),
      height: height ?? MediaQuery.sizeOf(context).height * 0.4,
      margin: const EdgeInsets.only(left: 6.0, right: 6.0, top: 12, bottom: 14),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8.0),
            child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 18)),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: GridView.builder(
              scrollDirection: Axis.horizontal,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                childAspectRatio: 0.25,
                crossAxisSpacing: 14,
                mainAxisSpacing: 14,
              ),
              itemCount: apps.length,
              itemBuilder: (context, index) => SectionAppItemCard(
                app: apps[index],
                index: index,
              ),
            ),
          ),
          const SizedBox(height: 16),
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
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          MixpanelManager().pageOpened('App Detail From Popular Apps Section');
          await routeToPage(context, AppDetailPage(app: app));
          provider.setApps();
        },
        child: Container(
          padding: const EdgeInsets.fromLTRB(12, 12, 10, 12),
          decoration: BoxDecoration(
            color: const Color.fromARGB(255, 25, 24, 24),
            borderRadius: BorderRadius.circular(12.0),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CachedNetworkImage(
                imageUrl: app.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: BorderRadius.circular(8),
                    image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                  ),
                ),
                placeholder: (context, url) => const SizedBox(
                  width: 52,
                  height: 52,
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                ),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.start,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      app.name,
                      maxLines: 1,
                      style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(top: 4.0),
                      child: Text(
                        app.category.decodeString,
                        maxLines: 2,
                        style: const TextStyle(color: Colors.grey, fontSize: 14),
                      ),
                    ),
                    app.ratingAvg != null || app.installs > 0
                        ? Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                app.ratingAvg != null
                                    ? Row(
                                        crossAxisAlignment: CrossAxisAlignment.center,
                                        children: [
                                          Text(app.getRatingAvg()!),
                                          const SizedBox(width: 4),
                                          const Icon(Icons.star, color: Colors.deepPurple, size: 16),
                                          Text('(${app.ratingCount})'),
                                          const SizedBox(width: 16),
                                        ],
                                      )
                                    : const SizedBox(),
                              ],
                            ),
                          )
                        : Container(),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    });
  }
}
