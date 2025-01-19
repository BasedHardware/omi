import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

import 'app_detail/app_detail.dart';

class AppListItem extends StatelessWidget {
  final App app;
  final int index;
  final bool showPrivateIcon;

  const AppListItem({super.key, required this.app, required this.index, this.showPrivateIcon = true});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          MixpanelManager().pageOpened('App Detail');
          await routeToPage(context, AppDetailPage(app: app));
          provider.setApps();
        },
        child: Container(
          padding: const EdgeInsets.all(12),
          margin: EdgeInsets.only(bottom: 8, left: 8, right: 8, top: index == 0 ? 24 : 0),
          decoration: BoxDecoration(
            color: Colors.grey[900],
            borderRadius: BorderRadius.circular(12.0),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CachedNetworkImage(
                imageUrl: app.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: BorderRadius.circular(8),
                    image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
                  ),
                ),
                placeholder: (context, url) => const SizedBox(
                  width: 40,
                  height: 40,
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                ),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      app.name.decodeString + (app.private && showPrivateIcon ? " 🔒".decodeString : ''),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      app.description.decodeString,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: Colors.grey,
                        fontSize: 12,
                      ),
                    ),
                    if (app.ratingAvg != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              app.getRatingAvg()!,
                              style: const TextStyle(fontSize: 12),
                            ),
                            const SizedBox(width: 2),
                            const Icon(Icons.star, color: Colors.deepPurple, size: 12),
                            const SizedBox(width: 2),
                            Text(
                              '(${app.ratingCount})',
                              style: const TextStyle(fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              provider.appLoading.isNotEmpty && index != -1 && provider.appLoading[index]
                  ? const Padding(
                      padding: EdgeInsets.all(10),
                      child: SizedBox(
                        height: 24,
                        width: 24,
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      ),
                    )
                  : IconButton(
                      icon: Icon(
                        app.enabled ? Icons.check : Icons.arrow_downward_rounded,
                        color: app.enabled ? Colors.white : Colors.grey,
                      ),
                      onPressed: () {
                        if (app.worksExternally() && !app.enabled) {
                          showDialog(
                            context: context,
                            builder: (c) => getDialog(
                              context,
                              () => Navigator.pop(context),
                              () async {
                                Navigator.pop(context);
                                await routeToPage(context, AppDetailPage(app: app));
                                provider.setApps();
                              },
                              'Authorize External App',
                              'Do you allow this app to access your memories, transcripts, and recordings? Your data will be sent to the app\'s server for processing.',
                              okButtonText: 'Confirm',
                            ),
                          );
                        } else {
                          provider.toggleApp(app.id.toString(), !app.enabled, index);
                        }
                      },
                    ),
            ],
          ),
        ),
      );
    });
  }
}
