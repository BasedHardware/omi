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
          padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
          margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
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
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.start,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          app.name.decodeString,
                          maxLines: 1,
                          style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                        ),
                        app.private && showPrivateIcon
                            ? const SizedBox(
                                width: 6,
                              )
                            : const SizedBox(),
                        app.private && showPrivateIcon
                            ? const Icon(Icons.lock, color: Colors.grey, size: 16)
                            : const SizedBox(),
                      ],
                    ),
                    SizedBox(height: app.ratingAvg != null ? 4 : 0),
                    Padding(
                      padding: const EdgeInsets.only(top: 4.0),
                      child: Text(
                        app.description.decodeString,
                        maxLines: 2,
                        style: const TextStyle(color: Colors.grey, fontSize: 14),
                      ),
                    ),
                    Row(
                      children: [
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
                                              const SizedBox(width: 4),
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
                  ],
                ),
              ),
              const SizedBox(width: 16),
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
