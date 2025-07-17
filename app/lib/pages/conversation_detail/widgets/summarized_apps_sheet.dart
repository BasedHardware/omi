import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
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
        return Consumer<ConversationDetailProvider>(
          builder: (context, provider, _) {
            final summarizedApp = provider.getSummarizedApp();
            final currentAppId = summarizedApp?.appId;
            final conversationId = provider.conversation.id;

            MixpanelManager().summarizedAppSheetViewed(
              conversationId: conversationId,
              currentSummarizedAppId: currentAppId,
            );

            return _SheetContainer(
              scrollController: scrollController,
              children: [
                const _SheetHeader(),
                Expanded(
                  child: _AppsList(
                    provider: provider,
                    currentAppId: currentAppId,
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

class _SheetContainer extends StatelessWidget {
  final ScrollController scrollController;
  final List<Widget> children;

  const _SheetContainer({
    required this.scrollController,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => Navigator.pop(context),
      child: Container(
        color: Colors.black,
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: Column(children: children),
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader();

  @override
  Widget build(BuildContext context) {
    return Column(
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
      ],
    );
  }
}

class _AppsList extends StatelessWidget {
  final ConversationDetailProvider provider;
  final String? currentAppId;

  const _AppsList({
    required this.provider,
    required this.currentAppId,
  });

  @override
  Widget build(BuildContext context) {
    final availableApps = provider.appsList.where((app) => app.worksWithMemories() && app.enabled).toList();

    return ListView(
      children: [
        // Auto option
        _AppListItem(
          app: null,
          isSelected: false,
          onTap: () => _handleAutoAppTap(context),
          trailingIcon: const Icon(Icons.autorenew, color: Colors.white, size: 20),
        ),

        // List of installed apps
        ...availableApps.map((app) => _AppListItem(
              app: app,
              isSelected: app.id == currentAppId,
              onTap: () => _handleAppTap(context, app),
            )),

        // Enable Apps option
        const _EnableAppsListItem(),
      ],
    );
  }

  void _handleAutoAppTap(BuildContext context) async {
    Navigator.pop(context);
    final provider = context.read<ConversationDetailProvider>();
    final previousAppId = provider.getSummarizedApp()?.appId;
    final conversationId = provider.conversation.id;

    MixpanelManager().summarizedAppSelected(
      conversationId: conversationId,
      selectedAppId: 'auto',
      previousAppId: previousAppId,
    );

    provider.clearSelectedAppForReprocessing();
    await provider.reprocessConversation();
    return;
  }

  void _handleAppTap(BuildContext context, App app) async {
    // Reprocess with the selected app
    final provider = context.read<ConversationDetailProvider>();
    final previousAppId = provider.getSummarizedApp()?.appId;
    final conversationId = provider.conversation.id;

    MixpanelManager().summarizedAppSelected(
      conversationId: conversationId,
      selectedAppId: app.id,
      previousAppId: previousAppId,
    );

    Navigator.pop(context);
    provider.setSelectedAppForReprocessing(app);
    provider.setPreferredSummarizationApp(app.id);
    await provider.reprocessConversation(appId: app.id);
    return;
  }
}

class _AppListItem extends StatelessWidget {
  final App? app;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? trailingIcon;

  const _AppListItem({
    required this.app,
    required this.isSelected,
    required this.onTap,
    this.trailingIcon,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: _buildLeadingIcon(),
      title: Text(
        app != null ? app!.name.decodeString : 'Auto',
        style: TextStyle(
          color: Colors.white,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
          fontSize: 16,
        ),
      ),
      subtitle: app != null
          ? Text(
              app!.description.decodeString,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            )
          : null,
      trailing: isSelected ? const Icon(Icons.check, color: Colors.white, size: 20) : trailingIcon,
      selected: isSelected,
      onTap: onTap,
    );
  }

  Widget _buildLeadingIcon() {
    if (app != null) {
      return CachedNetworkImage(
        imageUrl: app!.getImageUrl(),
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
      );
    } else {
      return Container(
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
      );
    }
  }
}

class _EnableAppsListItem extends StatelessWidget {
  const _EnableAppsListItem();

  @override
  Widget build(BuildContext context) {
    return ListTile(
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
        final conversationId = context.read<ConversationDetailProvider>().conversation.id;
        MixpanelManager().summarizedAppEnableAppsClicked(conversationId: conversationId);
        routeToPage(context, const AppsPage(showAppBar: true));
        MixpanelManager().pageOpened('Detail Apps');
      },
    );
  }
}
