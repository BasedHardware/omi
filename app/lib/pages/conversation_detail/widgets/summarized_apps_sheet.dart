import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

class SummarizedAppsBottomSheet extends StatelessWidget {
  const SummarizedAppsBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.5,
      maxChildSize: 0.9,
      expand: false,
      builder: (context, scrollController) {
        return GestureDetector(
          onTap: () => Navigator.pop(context),
          child: Consumer<ConversationDetailProvider>(
            builder: (context, provider, child) {
              final summarizedApp = provider.getSummarizedApp();
              final currentAppId = summarizedApp?.appId;

              return Container(
                color: Colors.black,
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: Column(
                  children: [
                    // Handle indicator
                    Container(
                      width: 40,
                      height: 4,
                      margin: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.grey[600],
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),

                    // Title
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Summarized Apps',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close),
                          onPressed: () => Navigator.pop(context),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    Expanded(
                      child: ListView(
                        controller: scrollController,
                        children: [
                          // Auto option
                          _buildAppItem(
                            context,
                            null,
                            currentAppId == null,
                            () async {
                              // If an app was previously selected, reprocess with no specific app
                              if (currentAppId != null) {
                                Navigator.pop(context);
                                final provider = context.read<ConversationDetailProvider>();
                                await provider.reprocessConversation();
                                return;
                              }
                              // Otherwise just close the sheet
                              Navigator.pop(context);
                            },
                          ),

                          // Enable Apps option
                          ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
                            leading: const Icon(Icons.apps, color: Colors.white, size: 24),
                            title: const Text(
                              'Enable Apps',
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w500,
                                fontSize: 16,
                              ),
                            ),
                            trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                            onTap: () {
                              Navigator.pop(context);
                              Navigator.pop(context);
                              context.read<HomeProvider>().setIndex(2);
                              if (context.read<HomeProvider>().onSelectedIndexChanged != null) {
                                context.read<HomeProvider>().onSelectedIndexChanged!(2);
                              }
                            },
                          ),

                          // List of installed apps
                          ...provider.appsList
                              .where((app) => app.worksWithMemories() && app.enabled)
                              .map((app) => _buildAppItem(
                                    context,
                                    app,
                                    app.id == currentAppId,
                                    () async {
                                      // If this is a different app than currently selected, reprocess with this app
                                      if (app.id != currentAppId) {
                                        Navigator.pop(context);
                                        final provider = context.read<ConversationDetailProvider>();
                                        provider.setSelectedAppForReprocessing(app);
                                        await provider.reprocessConversation(appId: app.id);
                                        return;
                                      }
                                      // Otherwise just show app details
                                      MixpanelManager().pageOpened('App Detail');
                                      routeToPage(context, AppDetailPage(app: app));
                                    },
                                  ))
                              .toList(),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildAppItem(
    BuildContext context,
    App? app,
    bool isSelected,
    VoidCallback onTap,
  ) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: app != null
          ? CachedNetworkImage(
              imageUrl: app.getImageUrl(),
              imageBuilder: (context, imageProvider) {
                return CircleAvatar(
                  backgroundColor: Colors.white,
                  radius: 16,
                  backgroundImage: imageProvider,
                );
              },
              errorWidget: (context, url, error) {
                return const CircleAvatar(
                  backgroundColor: Colors.white,
                  radius: 16,
                  child: Icon(Icons.error_outline_rounded, size: 16),
                );
              },
              progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
                backgroundColor: Colors.white,
                radius: 16,
                child: CircularProgressIndicator(
                  value: progress.progress,
                  valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                  strokeWidth: 2,
                ),
              ),
            )
          : Container(
              decoration: BoxDecoration(
                image: DecorationImage(
                  image: AssetImage(Assets.images.background.path),
                  fit: BoxFit.cover,
                ),
                borderRadius: const BorderRadius.all(Radius.circular(16.0)),
              ),
              height: 32,
              width: 32,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Image.asset(
                    Assets.images.herologo.path,
                    height: 20,
                    width: 20,
                  ),
                ],
              ),
            ),
      title: Text(
        app != null ? app.name : 'Auto',
        style: TextStyle(
          color: Colors.white,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
          fontSize: 16,
        ),
      ),
      subtitle: app != null
          ? Text(
              app.description,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            )
          : null,
      trailing: isSelected ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
      selected: isSelected,
      onTap: onTap,
    );
  }
}
