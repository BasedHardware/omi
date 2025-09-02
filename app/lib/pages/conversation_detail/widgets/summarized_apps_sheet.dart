import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
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
              'Conversation Analysis',
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

  // Track app installation state
  static final Map<String, bool> _installingApps = {};

  @override
  Widget build(BuildContext context) {
    final availableApps = provider.appsList.where((app) => app.worksWithMemories() && app.enabled).toList();
    final suggestedAppIds = provider.getSuggestedApps();
    final lastUsedApp = provider.getLastUsedSummarizationApp();

    // Convert suggested app IDs to App objects
    final suggestedApps = suggestedAppIds
        .map((appId) => provider.appsList.firstWhereOrNull((app) => app.id == appId))
        .where((app) => app != null)
        .cast<App>()
        .toList();

    // Filter out suggested apps and last used app from other apps
    final otherApps = availableApps
        .where((app) => !provider.isAppSuggested(app.id) && (lastUsedApp == null || app.id != lastUsedApp.id))
        .toList();

    return ListView(
      children: [
        // Auto option
        _AppListItem(
          app: null,
          isSelected: currentAppId == null,
          onTap: () => _handleAutoAppTap(context),
          trailingIcon: const Icon(Icons.autorenew, color: Colors.white, size: 20),
          subtitle: 'Let Omi automatically choose the best app for this summary.',
          provider: provider,
        ),

        // Suggested Apps section
        if (suggestedApps.isNotEmpty) ...[
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              'Suggested Apps',
              style: TextStyle(
                color: Colors.grey,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ...suggestedApps.map((app) {
            final isAvailable = provider.isSuggestedAppAvailable(app.id);
            final isInstalling = _AppsList._installingApps[app.id] == true;
            return _AppListItem(
              app: app,
              isSelected: app.id == currentAppId,
              onTap: () => isAvailable ? _handleAppTap(context, app) : _handleUnavailableAppTap(context, app),
              isSuggested: true,
              isInstalling: isInstalling,
              provider: provider,
            );
          }),
        ],

        // Other Apps section (includes last used app at top)
        if (otherApps.isNotEmpty || lastUsedApp != null) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              suggestedApps.isNotEmpty ? 'Other Apps' : 'Available Apps',
              style: const TextStyle(
                color: Colors.grey,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          // Show last used app first if available
          if (lastUsedApp != null)
            _AppListItem(
              app: lastUsedApp,
              isSelected: lastUsedApp.id == currentAppId,
              onTap: () => _handleAppTap(context, lastUsedApp),
              isLastUsed: true,
              provider: provider,
            ),
          // Then show other apps
          ...otherApps.map((app) => _AppListItem(
                app: app,
                isSelected: app.id == currentAppId,
                onTap: () => _handleAppTap(context, app),
                provider: provider,
              )),
        ],

        // Create Template option
        const _CreateTemplateListItem(),

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

    // Track the last used app
    provider.trackLastUsedSummarizationApp(app.id);

    Navigator.pop(context);
    provider.setSelectedAppForReprocessing(app);
    await provider.reprocessConversation(appId: app.id);
    return;
  }

  void _handleUnavailableAppTap(BuildContext context, App app) async {
    // Check if app is already being installed
    if (_AppsList._installingApps[app.id] == true) {
      return;
    }

    // Set installing state
    _AppsList._installingApps[app.id] = true;

    try {
      final appProvider = context.read<AppProvider>();
      final conversationProvider = context.read<ConversationDetailProvider>();
      final conversationId = conversationProvider.conversation.id;

      // Find the app index in the apps list for toggleApp
      final appIndex = appProvider.apps.indexWhere((a) => a.id == app.id);

      // Install/enable the app
      await appProvider.toggleApp(app.id, true, appIndex >= 0 ? appIndex : null);

      // Check if installation was successful
      final installedApp = appProvider.apps.firstWhereOrNull((a) => a.id == app.id && a.enabled);

      if (installedApp != null) {
        // Track analytics
        MixpanelManager().summarizedAppSelected(
          conversationId: conversationId,
          selectedAppId: app.id,
          previousAppId: conversationProvider.getSummarizedApp()?.appId,
        );

        // Track the last used app
        conversationProvider.trackLastUsedSummarizationApp(app.id);

        // Close the bottom sheet
        Navigator.pop(context);

        // Set the app for reprocessing and reprocess the conversation
        conversationProvider.setSelectedAppForReprocessing(installedApp);
        await conversationProvider.reprocessConversation(appId: app.id);
      } else {
        // Installation failed
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to install ${app.name}. Please try again.'),
            duration: const Duration(seconds: 3),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      // Handle installation error
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error installing ${app.name}: ${e.toString()}'),
          duration: const Duration(seconds: 3),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      // Clear installing state
      _AppsList._installingApps[app.id] = false;
    }
  }
}

class _AppListItem extends StatelessWidget {
  final App? app;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? trailingIcon;
  final String? subtitle;
  final bool isSuggested;
  final bool isLastUsed;
  final bool isInstalling;
  final ConversationDetailProvider? provider;

  const _AppListItem({
    required this.app,
    required this.isSelected,
    required this.onTap,
    this.trailingIcon,
    this.subtitle,
    this.isSuggested = false,
    this.isLastUsed = false,
    this.isInstalling = false,
    this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: _buildLeadingIcon(),
      title: Row(
        children: [
          Expanded(
            child: Text(
              app != null ? app!.name.decodeString : 'Auto',
              style: TextStyle(
                color: Colors.white,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                fontSize: 16,
              ),
            ),
          ),
          if (isLastUsed)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withValues(alpha: 0.3)),
              ),
              child: const Text(
                'Last Used',
                style: TextStyle(
                  color: Colors.black,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
      subtitle: app != null
          ? Text(
              app!.description.decodeString,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            )
          : subtitle != null
              ? Text(
                  subtitle!,
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                )
              : null,
      trailing: _buildTrailingWidget(),
      selected: isSelected,
      onTap: onTap,
    );
  }

  Widget _buildTrailingWidget() {
    // Check if this app is currently being processed
    final isProcessing = provider != null &&
        provider!.loadingReprocessConversation &&
        ((app != null && provider!.selectedAppForReprocessing?.id == app!.id) ||
            (app == null && provider!.selectedAppForReprocessing == null));

    if (isSelected) {
      return const Icon(Icons.check, color: Colors.green, size: 20);
    } else if (isInstalling) {
      return const SizedBox(
        width: 20,
        height: 20,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      );
    } else if (isProcessing) {
      return const SizedBox(
        width: 20,
        height: 20,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      );
    } else {
      return trailingIcon ?? const SizedBox.shrink();
    }
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

class _CreateTemplateListItem extends StatelessWidget {
  const _CreateTemplateListItem();

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        Navigator.pop(context);
        final conversationId = context.read<ConversationDetailProvider>().conversation.id;
        MixpanelManager().summarizedAppCreateTemplateClicked(conversationId: conversationId);

        // Navigate to AddAppPage with preset values for template creation
        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => const AddAppPage(presetForConversationAnalysis: true),
          ),
        );

        MixpanelManager().pageOpened('Create Template from Conversation');
      },
      child: Container(
        padding: const EdgeInsets.all(20),
        margin: const EdgeInsets.fromLTRB(16, 8, 16, 8),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.9),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.auto_fix_high,
                color: Colors.white,
                size: 20,
              ),
            ),
            const SizedBox(width: 16),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Create Custom Template',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: Colors.black,
                    ),
                  ),
                  SizedBox(height: 2),
                  Text(
                    'Build a personalized analysis app for your conversations',
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.black54,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right,
              color: Colors.black,
              size: 24,
            ),
          ],
        ),
      ),
    );
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
        'Explore',
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

        // Try to route to conversation-analysis category first
        final appProvider = context.read<AppProvider>();
        final conversationAnalysisCategory = appProvider.categories.firstWhereOrNull(
          (category) => category.id == 'conversation-analysis',
        );

        if (conversationAnalysisCategory != null) {
          final categoryApps = appProvider.apps.where((app) => app.category == 'conversation-analysis').toList();
          routeToPage(
              context,
              CategoryAppsPage(
                category: conversationAnalysisCategory,
                apps: categoryApps,
              ));
        } else {
          // Fallback to general apps page
          routeToPage(context, const AppsPage(showAppBar: true));
        }
        MixpanelManager().pageOpened('Detail Apps');
      },
    );
  }
}
