import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/create_template_bottom_sheet.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

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
              'Summary Template',
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

class _AppsList extends StatefulWidget {
  final ConversationDetailProvider provider;
  final String? currentAppId;

  const _AppsList({
    required this.provider,
    required this.currentAppId,
  });

  @override
  State<_AppsList> createState() => _AppsListState();
}

class _AppsListState extends State<_AppsList> {
  // Track app installation state
  static final Map<String, bool> _installingApps = {};

  @override
  void initState() {
    super.initState();
    _fetchApps();
    // Listen to provider changes to rebuild when apps are fetched
    widget.provider.addListener(_onProviderUpdate);
  }

  @override
  void dispose() {
    widget.provider.removeListener(_onProviderUpdate);
    super.dispose();
  }

  void _onProviderUpdate() {
    if (mounted) {
      setState(() {});
    }
  }

  Future<void> _fetchApps() async {
    try {
      await Future.wait([
        widget.provider.fetchAndCacheSuggestedApps(),
        widget.provider.fetchAndCacheEnabledConversationApps(),
      ]);
    } catch (e) {
      debugPrint('Error fetching apps: $e');
    }
  }

  Widget _buildShimmerLoading() {
    return ListView(
      children: [
        // Auto option shimmer
        _buildShimmerListItem(),

        // Suggested Apps section shimmer
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            'Suggested Templates',
            style: TextStyle(
              color: Colors.grey,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        _buildShimmerListItem(),
        _buildShimmerListItem(),

        // Other Apps section shimmer
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            'Available Apps',
            style: TextStyle(
              color: Colors.grey,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        _buildShimmerListItem(),
        _buildShimmerListItem(),
        _buildShimmerListItem(),
      ],
    );
  }

  Widget _buildShimmerListItem() {
    return Shimmer.fromColors(
      baseColor: const Color(0xFF1F1F25),
      highlightColor: const Color(0xFF35343B),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            // Leading icon placeholder
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: const Color(0xFF1F1F25),
                borderRadius: BorderRadius.circular(16),
              ),
            ),
            const SizedBox(width: 16),
            // Title and subtitle placeholders
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    height: 16,
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1F25),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    width: 200,
                    height: 12,
                    decoration: BoxDecoration(
                      color: const Color(0xFF1F1F25),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final enabledApps = widget.provider.cachedEnabledConversationApps;
    final suggestedApps = widget.provider.cachedSuggestedApps;

    final isLoading = enabledApps.isEmpty && suggestedApps.isEmpty;

    if (isLoading) {
      return _buildShimmerLoading();
    }

    // Get preferred (default) app ID and find it in enabled apps
    final preferredAppId = widget.provider.preferredSummarizationAppId;
    final preferredApp = preferredAppId != null && preferredAppId.isNotEmpty
        ? enabledApps.firstWhereOrNull((app) => app.id == preferredAppId)
        : null;

    // Get last used app ID and find it in the enabled apps
    final lastUsedAppId = widget.provider.getLastUsedSummarizationAppId();
    final lastUsedApp = lastUsedAppId != null ? enabledApps.firstWhereOrNull((app) => app.id == lastUsedAppId) : null;

    final suggestedAppIds = suggestedApps.map((app) => app.id).toList();
    final currentUserId = SharedPreferencesUtil().uid;

    // Get other apps (excluding suggested, preferred, and last used)
    var otherApps = enabledApps
        .where((app) =>
            !suggestedAppIds.contains(app.id) &&
            (preferredApp == null || app.id != preferredApp.id) &&
            (lastUsedApp == null || app.id != lastUsedApp.id))
        .toList();

    // Sort: user's own apps first, then alphabetically by name
    otherApps.sort((a, b) {
      final aIsOwned = a.isOwner(currentUserId);
      final bIsOwned = b.isOwner(currentUserId);
      if (aIsOwned && !bIsOwned) return -1;
      if (!aIsOwned && bIsOwned) return 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });

    return ListView(
      children: [
        // Suggested Apps section
        if (suggestedApps.isNotEmpty) ...[
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              'Suggested Templates',
              style: TextStyle(
                color: Colors.grey,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ...suggestedApps.map((app) {
            final isAvailable = widget.provider.isSuggestedAppAvailable(app.id);
            final isInstalling = _AppsListState._installingApps[app.id] == true;
            return _AppListItem(
              app: app,
              isSelected: app.id == widget.currentAppId,
              onTap: () => isAvailable ? _handleAppTap(context, app) : _handleUnavailableAppTap(context, app),
              isSuggested: true,
              isDefault: app.id == preferredAppId && preferredAppId?.isNotEmpty == true,
              isInstalling: isInstalling,
              provider: widget.provider,
            );
          }),
        ],

        // Other Apps section (order: default app, last used, then others)
        if (otherApps.isNotEmpty || lastUsedApp != null || preferredApp != null) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              suggestedApps.isNotEmpty ? 'Other Templates' : 'Available Templates',
              style: const TextStyle(
                color: Colors.grey,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          // 1. Show default/preferred app first if available (and not in suggested)
          if (preferredApp != null && !suggestedAppIds.contains(preferredApp.id))
            _AppListItem(
              app: preferredApp,
              isSelected: preferredApp.id == widget.currentAppId,
              onTap: () => _handleAppTap(context, preferredApp),
              isDefault: true,
              provider: widget.provider,
            ),
          // 2. Show last used app second if available (and different from preferred)
          if (lastUsedApp != null && lastUsedApp.id != preferredAppId)
            _AppListItem(
              app: lastUsedApp,
              isSelected: lastUsedApp.id == widget.currentAppId,
              onTap: () => _handleAppTap(context, lastUsedApp),
              isLastUsed: true,
              isDefault: false,
              provider: widget.provider,
            ),
          // 3. Then show other apps (user's own apps first, then alphabetically)
          ...otherApps.map((app) => _AppListItem(
                app: app,
                isSelected: app.id == widget.currentAppId,
                onTap: () => _handleAppTap(context, app),
                isDefault: false,
                provider: widget.provider,
              )),
        ],

        // Get Creative section
        const Padding(
          padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            'Get Creative',
            style: TextStyle(
              color: Colors.grey,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),

        // Create Template option
        const _CreateTemplateListItem(),

        // All Templates option
        const _EnableAppsListItem(),
      ],
    );
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
    if (_AppsListState._installingApps[app.id] == true) {
      return;
    }

    // Set installing state
    setState(() {
      _AppsListState._installingApps[app.id] = true;
    });

    try {
      final conversationProvider = context.read<ConversationDetailProvider>();
      final conversationId = conversationProvider.conversation.id;

      final success = await conversationProvider.enableApp(app);

      if (!success) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to install ${app.name}. Please try again.'),
              duration: const Duration(seconds: 3),
              backgroundColor: Colors.red,
            ),
          );
        }
        return;
      }

      // Track analytics
      MixpanelManager().summarizedAppSelected(
        conversationId: conversationId,
        selectedAppId: app.id,
        previousAppId: conversationProvider.getSummarizedApp()?.appId,
      );

      // Track the last used app
      conversationProvider.trackLastUsedSummarizationApp(app.id);

      // Close the bottom sheet
      if (mounted) Navigator.pop(context);

      // Set the app for reprocessing and reprocess the conversation
      conversationProvider.setSelectedAppForReprocessing(app);
      await conversationProvider.reprocessConversation(appId: app.id);
    } catch (e) {
      // Handle installation error
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error installing ${app.name}: ${e.toString()}'),
            duration: const Duration(seconds: 3),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      // Clear installing state
      if (mounted) {
        setState(() {
          _AppsListState._installingApps[app.id] = false;
        });
      }
    }
  }
}

class _AppListItem extends StatefulWidget {
  final App app;
  final bool isSelected;
  final VoidCallback onTap;
  final bool isSuggested;
  final bool isLastUsed;
  final bool isDefault;
  final bool isInstalling;
  final ConversationDetailProvider? provider;

  const _AppListItem({
    required this.app,
    required this.isSelected,
    required this.onTap,
    this.isSuggested = false,
    this.isLastUsed = false,
    this.isDefault = false,
    this.isInstalling = false,
    this.provider,
  });

  @override
  State<_AppListItem> createState() => _AppListItemState();
}

class _AppListItemState extends State<_AppListItem> {
  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: Key('dismissible_${widget.app.id}'),
      direction: DismissDirection.horizontal,
      confirmDismiss: (direction) async {
        // Show confirmation dialog
        final confirmed = await _showSetDefaultConfirmation(context);

        if (confirmed == true) {
          // Set as preferred app
          if (widget.provider != null) {
            widget.provider!.setPreferredSummarizationApp(widget.app.id);
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('${widget.app.name.decodeString} set as default summarization app'),
                  duration: const Duration(seconds: 2),
                ),
              );
            }
          }
        }

        // Always return false to prevent dismissal - we just want the swipe action, not removal
        return false;
      },
      background: _buildSwipeBackground(isLeft: true),
      secondaryBackground: _buildSwipeBackground(isLeft: false),
      child: _buildListTile(),
    );
  }

  Future<bool?> _showSetDefaultConfirmation(BuildContext context) {
    return showCupertinoDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return CupertinoAlertDialog(
          title: const Text('Set Default App'),
          content: Padding(
            padding: const EdgeInsets.only(top: 8.0),
            child: Text(
              'Set ${widget.app.name.decodeString} as your default summarization app?\n\nThis app will be automatically used for all future conversation summaries.',
            ),
          ),
          actions: [
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Set Default'),
            ),
          ],
        );
      },
    );
  }

  Widget _buildSwipeBackground({required bool isLeft}) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: isLeft ? Alignment.centerLeft : Alignment.centerRight,
          end: isLeft ? Alignment.centerRight : Alignment.centerLeft,
          colors: [
            Colors.deepPurple.withValues(alpha: 0.7),
            Colors.transparent,
          ],
        ),
      ),
      alignment: isLeft ? Alignment.centerLeft : Alignment.centerRight,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.star_rounded,
            color: Colors.amber.shade300,
            size: 20,
          ),
          const SizedBox(height: 2),
          const Text(
            'Default',
            style: TextStyle(
              color: Colors.white70,
              fontWeight: FontWeight.w600,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildListTile() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          leading: _buildLeadingIcon(),
          title: Text(
            widget.app.name.decodeString,
            style: TextStyle(
              color: Colors.white,
              fontWeight: widget.isSelected ? FontWeight.bold : FontWeight.w500,
              fontSize: 16,
            ),
          ),
          subtitle: _buildSubtitle(),
          trailing: _buildTrailingWidget(),
          selected: widget.isSelected,
          onTap: widget.onTap,
        ),
        Divider(
          height: 1,
          thickness: 0.5,
          color: Colors.grey.withValues(alpha: 0.2),
          indent: 56,
          endIndent: 16,
        ),
      ],
    );
  }

  Widget? _buildSubtitle() {
    // Build tags row for apps
    final List<Widget> tags = [];

    if (widget.isDefault) {
      tags.add(
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.amber.shade300.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 1, 0, 0),
                  child: Icon(
                    FontAwesomeIcons.solidStar,
                    size: 7,
                    color: Colors.amber.shade300,
                  ),
                ),
                const SizedBox(width: 4),
                Text(
                  'Default',
                  style: TextStyle(
                    color: Colors.amber.shade300,
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (widget.isLastUsed && !widget.isDefault) {
      tags.add(
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          decoration: BoxDecoration(
            color: Colors.grey.shade600.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 1, 0, 0),
                  child: Icon(
                    FontAwesomeIcons.clock,
                    size: 7,
                    color: Colors.grey.shade400,
                  ),
                ),
                const SizedBox(width: 4),
                Text(
                  'Last Used',
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (tags.isEmpty) {
      return null;
    }

    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: tags,
      ),
    );
  }

  Widget _buildTrailingWidget() {
    // Check if this app is currently being processed
    final isProcessing = widget.provider != null &&
        widget.provider!.loadingReprocessConversation &&
        widget.provider!.selectedAppForReprocessing?.id == widget.app.id;

    if (widget.isSelected) {
      return const Icon(Icons.check, color: Colors.green, size: 20);
    } else if (widget.isInstalling) {
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
      return const SizedBox.shrink();
    }
  }

  Widget _buildLeadingIcon() {
    return CachedNetworkImage(
      imageUrl: widget.app.getImageUrl(),
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
  }
}

class _CreateTemplateListItem extends StatelessWidget {
  const _CreateTemplateListItem();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          leading: const CircleAvatar(
            backgroundColor: Colors.white,
            radius: 16,
            child: Icon(
              FontAwesomeIcons.plus,
              color: Colors.black,
              size: 18,
            ),
          ),
          title: const Text(
            'Create Custom Template',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w500,
              fontSize: 16,
            ),
          ),
          trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
          onTap: () {
            final conversationId = context.read<ConversationDetailProvider>().conversation.id;
            MixpanelManager().summarizedAppCreateTemplateClicked(conversationId: conversationId);

            // Close the current bottom sheet first
            Navigator.pop(context);

            // Show the quick create template bottom sheet
            showCreateTemplateBottomSheet(context, conversationId: conversationId);
          },
        ),
        Divider(
          height: 1,
          thickness: 0.5,
          color: Colors.grey.withValues(alpha: 0.2),
          indent: 56,
          endIndent: 16,
        ),
      ],
    );
  }
}

class _EnableAppsListItem extends StatelessWidget {
  const _EnableAppsListItem();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
          leading: const CircleAvatar(
            backgroundColor: Colors.white,
            radius: 16,
            child: FaIcon(
              FontAwesomeIcons.solidFolderOpen,
              color: Colors.black,
              size: 14,
            ),
          ),
          title: const Text(
            'All Templates',
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

            // Navigate to Summary (memories) capability apps page
            final appProvider = context.read<AppProvider>();
            final memoriesApps = appProvider.apps.where((app) => app.worksWithMemories()).toList();

            routeToPage(
              context,
              CapabilityAppsPage(
                capability: AppCapability(
                  title: 'Summary',
                  id: 'memories',
                ),
                apps: memoriesApps,
              ),
            );
            MixpanelManager().pageOpened('Summary Apps');
          },
        ),
        Divider(
          height: 1,
          thickness: 0.5,
          color: Colors.grey.withValues(alpha: 0.2),
          indent: 56,
          endIndent: 16,
        ),
      ],
    );
  }
}
