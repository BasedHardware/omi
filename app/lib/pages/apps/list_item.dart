import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

import 'app_detail/app_detail.dart';

class AppListItem extends StatelessWidget {
  final App app;
  final int index;
  final bool showPrivateIcon;

  const AppListItem({super.key, required this.app, required this.index, this.showPrivateIcon = true});

  @override
  Widget build(BuildContext context) {
    // Use Selector to only rebuild when this specific app's state or loading state changes
    return Selector<AppProvider, ({bool enabled, bool isLoading})>(
      selector: (context, provider) {
        // Find the current app state
        final currentApp = provider.apps.firstWhere(
          (a) => a.id == app.id,
          orElse: () => app,
        );

        // Check if this specific app is loading
        final isLoading = index != -1 &&
            provider.appLoading.isNotEmpty &&
            index < provider.appLoading.length &&
            provider.appLoading[index];

        return (enabled: currentApp.enabled, isLoading: isLoading);
      },
      builder: (context, state, child) {
        return GestureDetector(
          onTap: () async {
            MixpanelManager().pageOpened('App Detail');
            await routeToPage(context, AppDetailPage(app: app));
            context.read<AppProvider>().setApps();
          },
          child: Container(
            padding: const EdgeInsets.all(16),
            margin: EdgeInsets.only(bottom: 8, top: index == 0 ? 16 : 0),
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25).withOpacity(0.3),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                // App icon - Apple style square with rounded corners
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      color: Color(0xFF35343B),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: CachedNetworkImage(
                      imageUrl: app.getImageUrl(),
                      httpHeaders: const {
                        "User-Agent":
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                      },
                      fit: BoxFit.cover,
                      placeholder: (context, url) => Center(
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.grey.shade600),
                          strokeWidth: 2,
                        ),
                      ),
                      errorWidget: (context, url, error) => Icon(
                        Icons.apps,
                        size: 30,
                        color: Colors.grey.shade600,
                      ),
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
                        app.name.decodeString + (app.private && showPrivateIcon ? " 🔒".decodeString : ''),
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                          color: Colors.white,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        app.description.length > 50 ? '${app.description.substring(0, 50)}...' : app.description,
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.grey.shade400,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),

                const SizedBox(width: 12),

                // Action button - Apple style
                state.isLoading
                    ? Container(
                        width: 72,
                        height: 32,
                        decoration: BoxDecoration(
                          color: Colors.grey.shade700,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const Center(
                          child: SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              strokeWidth: 2,
                            ),
                          ),
                        ),
                      )
                    : GestureDetector(
                        onTap: () {
                          if (state.enabled) {
                            // App is enabled, open app detail
                            MixpanelManager().pageOpened('App Detail');
                            routeToPage(context, AppDetailPage(app: app));
                            return;
                          }

                          // App is not enabled, toggle it on
                          if (app.worksExternally()) {
                            showDialog(
                              context: context,
                              builder: (c) => getDialog(
                                context,
                                () => Navigator.pop(context),
                                () async {
                                  Navigator.pop(context);
                                  context.read<AppProvider>().toggleApp(app.id.toString(), true, index);
                                },
                                'Authorize External App',
                                'Do you allow this app to access your memories, transcripts, and recordings? Your data will be sent to the app\'s server for processing.',
                                okButtonText: 'Confirm',
                              ),
                            );
                          } else {
                            context.read<AppProvider>().toggleApp(app.id.toString(), true, index);
                          }
                        },
                        child: Container(
                          width: 72,
                          height: 32,
                          decoration: BoxDecoration(
                            color: state.enabled ? Colors.grey.shade700 : Color(0xFF8B5CF6),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Center(
                            child: Text(
                              state.enabled ? 'Open' : 'Get',
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
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
