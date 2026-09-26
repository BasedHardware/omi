import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/create_template_bottom_sheet.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Opens the summary-template picker for the conversation on screen.
Future<void> showSummarizedAppsSheet(BuildContext context) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.summaryTemplate,
    padding: EdgeInsets.zero,
    builder: (_) => const SummarizedAppsBottomSheet(),
  );
}

/// Body of the summary-template picker; present it with [showSummarizedAppsSheet].
class SummarizedAppsBottomSheet extends StatelessWidget {
  const SummarizedAppsBottomSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.7,
      child: Consumer<ConversationDetailProvider>(
        builder: (context, provider, _) {
          final currentSelection = provider.getSummarySelection();
          final currentAppId = currentSelection.isApp ? currentSelection.appId : null;

          PlatformManager.instance.analytics.summarizedAppSheetViewed(
            conversationId: provider.conversation.id,
            currentSummarizedAppId: currentAppId,
          );

          return _AppsList(provider: provider, currentAppId: currentAppId);
        },
      ),
    );
  }
}

class _AppsList extends StatefulWidget {
  final ConversationDetailProvider provider;
  final String? currentAppId;

  const _AppsList({required this.provider, required this.currentAppId});

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

  // The fetch is done, whatever it came back with. Without this flag "empty" and
  // "still loading" are indistinguishable: both fetches swallow their errors into
  // empty lists, so the sheet stayed in the skeleton forever for anyone without a
  // single installed template.
  bool _loaded = false;

  Future<void> _fetchApps() async {
    try {
      await Future.wait([
        widget.provider.fetchAndCacheSuggestedApps(),
        widget.provider.fetchAndCacheEnabledConversationApps(),
      ]);
    } catch (e) {
      Logger.debug('Error fetching apps: $e');
    } finally {
      if (mounted) {
        setState(() => _loaded = true);
      }
    }
  }

  Widget _buildShimmerLoading() {
    return ListView(
      children: [
        // Auto option shimmer
        _buildShimmerListItem(),

        // Suggested Apps section shimmer
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            context.l10n.suggestedTemplates,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
          ),
        ),
        _buildShimmerListItem(),
        _buildShimmerListItem(),

        // Other Apps section shimmer
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            context.l10n.availableTemplates,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
          ),
        ),
        _buildShimmerListItem(),
        _buildShimmerListItem(),
        _buildShimmerListItem(),
      ],
    );
  }

  Widget _buildShimmerListItem() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface3,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Row(
          children: [
            // Leading icon placeholder
            Container(
              width: 32,
              height: 32,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
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
                    decoration: const BoxDecoration(
                        color: OmiColors.surface1, borderRadius: BorderRadius.all(Radius.circular(4))),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    width: 200,
                    height: 12,
                    decoration: const BoxDecoration(
                        color: OmiColors.surface1, borderRadius: BorderRadius.all(Radius.circular(4))),
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

    final isLoading = !_loaded && enabledApps.isEmpty && suggestedApps.isEmpty;

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
        .where(
          (app) =>
              !suggestedAppIds.contains(app.id) &&
              (preferredApp == null || app.id != preferredApp.id) &&
              (lastUsedApp == null || app.id != lastUsedApp.id),
        )
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
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              context.l10n.suggestedTemplates,
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
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
              suggestedApps.isNotEmpty ? context.l10n.otherTemplates : context.l10n.availableTemplates,
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
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
          ...otherApps.map(
            (app) => _AppListItem(
              app: app,
              isSelected: app.id == widget.currentAppId,
              onTap: () => _handleAppTap(context, app),
              isDefault: false,
              provider: widget.provider,
            ),
          ),
        ],

        // Get Creative section
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Text(
            context.l10n.getCreative,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
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
    final previousSelection = provider.getSummarySelection();
    final previousAppId = previousSelection.isApp ? previousSelection.appId : null;
    final conversationId = provider.conversation.id;

    PlatformManager.instance.analytics.summarizedAppSelected(
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
        if (context.mounted) {
          OmiFeedback.error(context, context.l10n.failedToInstallApp(app.name));
        }
        return;
      }

      // Track analytics
      PlatformManager.instance.analytics.summarizedAppSelected(
        conversationId: conversationId,
        selectedAppId: app.id,
        previousAppId:
            conversationProvider.getSummarySelection().isApp ? conversationProvider.getSummarySelection().appId : null,
      );

      // Track the last used app
      conversationProvider.trackLastUsedSummarizationApp(app.id);

      // Close the bottom sheet
      if (context.mounted) Navigator.pop(context);

      // Set the app for reprocessing and reprocess the conversation
      conversationProvider.setSelectedAppForReprocessing(app);
      await conversationProvider.reprocessConversation(appId: app.id);
    } catch (e) {
      // Handle installation error
      if (context.mounted) {
        OmiFeedback.error(context, context.l10n.errorInstallingApp(app.name, e.toString()));
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
            final saved = await widget.provider!.setPreferredSummarizationApp(widget.app.id);
            if (context.mounted) {
              if (saved) {
                OmiFeedback.confirm(context, context.l10n.setAsDefaultSuccess(widget.app.name.decodeString));
              } else {
                OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
              }
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

  Future<bool> _showSetDefaultConfirmation(BuildContext context) {
    return showOmiConfirm(
      context,
      title: context.l10n.setDefaultApp,
      message: context.l10n.setDefaultAppContent(widget.app.name.decodeString),
      confirmLabel: context.l10n.setDefaultButton,
    );
  }

  Widget _buildSwipeBackground({required bool isLeft}) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: isLeft ? Alignment.centerLeft : Alignment.centerRight,
          end: isLeft ? Alignment.centerRight : Alignment.centerLeft,
          colors: const [OmiColors.surface3, Colors.transparent],
        ),
      ),
      alignment: isLeft ? Alignment.centerLeft : Alignment.centerRight,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star_rounded, color: Colors.amber.shade300, size: 20),
          const SizedBox(height: 2),
          Text(
            context.l10n.defaultLabel,
            style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
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
            style: OmiType.callout.copyWith(fontWeight: widget.isSelected ? FontWeight.bold : FontWeight.w500),
          ),
          subtitle: _buildSubtitle(),
          trailing: _buildTrailingWidget(),
          selected: widget.isSelected,
          onTap: widget.onTap,
        ),
        const Divider(height: 1, thickness: 0.5, color: OmiColors.border, indent: 56, endIndent: 16),
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
            borderRadius: OmiRadius.smAll,
          ),
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 1, 0, 0),
                  child: FaIcon(FontAwesomeIcons.solidStar, size: 7, color: Colors.amber.shade300),
                ),
                const SizedBox(width: 4),
                Text(
                  context.l10n.defaultLabel,
                  style: OmiType.caption.copyWith(color: Colors.amber.shade300, fontWeight: FontWeight.w600),
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
            borderRadius: OmiRadius.smAll,
          ),
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(0, 1, 0, 0),
                  child: FaIcon(FontAwesomeIcons.clock, size: 7, color: Colors.grey.shade400),
                ),
                const SizedBox(width: 4),
                Text(
                  context.l10n.lastUsedLabel,
                  style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
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
      child: Row(children: tags),
    );
  }

  Widget _buildTrailingWidget() {
    // Check if this app is currently being processed
    final isProcessing = widget.provider != null &&
        widget.provider!.loadingReprocessConversation &&
        widget.provider!.selectedAppForReprocessing?.id == widget.app.id;

    if (widget.isSelected) {
      return const Icon(Icons.check, color: OmiColors.textPrimary, size: 20);
    } else if (widget.isInstalling || isProcessing) {
      return const OmiSpinner(size: OmiSpinnerSize.small);
    } else {
      return const SizedBox.shrink();
    }
  }

  Widget _buildLeadingIcon() {
    return CachedNetworkImage(
      imageUrl: widget.app.getImageUrl(),
      imageBuilder: (context, imageProvider) {
        return CircleAvatar(backgroundColor: Colors.white, radius: 16, backgroundImage: imageProvider);
      },
      errorWidget: (context, url, error) {
        return const CircleAvatar(
          backgroundColor: Colors.white,
          radius: 16,
          child: Icon(Icons.error_outline_rounded, size: 16),
        );
      },
      progressIndicatorBuilder: (context, url, progress) => const CircleAvatar(
        backgroundColor: OmiColors.surface2,
        radius: 16,
        child: OmiSpinner(size: OmiSpinnerSize.small),
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
            child: FaIcon(FontAwesomeIcons.plus, color: Colors.black, size: 18),
          ),
          title: Text(
            context.l10n.createCustomTemplate,
            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
          ),
          trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
          onTap: () {
            final conversationId = context.read<ConversationDetailProvider>().conversation.id;
            PlatformManager.instance.analytics.summarizedAppCreateTemplateClicked(conversationId: conversationId);

            // Close the current bottom sheet first
            Navigator.pop(context);

            // Show the quick create template bottom sheet
            showCreateTemplateBottomSheet(context, conversationId: conversationId);
          },
        ),
        const Divider(height: 1, thickness: 0.5, color: OmiColors.border, indent: 56, endIndent: 16),
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
            child: FaIcon(FontAwesomeIcons.solidFolderOpen, color: Colors.black, size: 14),
          ),
          title: Text(
            context.l10n.allTemplates,
            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
          ),
          trailing: const Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
          onTap: () {
            Navigator.pop(context);
            final conversationId = context.read<ConversationDetailProvider>().conversation.id;
            PlatformManager.instance.analytics.summarizedAppEnableAppsClicked(conversationId: conversationId);

            // Navigate to Summary (memories) capability apps page
            final appProvider = context.read<AppProvider>();
            final memoriesApps = appProvider.apps.where((app) => app.worksWithMemories()).toList();

            routeToPage(
              context,
              CapabilityAppsPage(
                capability: AppCapability(title: context.l10n.summary, id: 'memories'),
                apps: memoriesApps,
              ),
            );
            PlatformManager.instance.analytics.pageOpened('Summary Apps');
          },
        ),
        const Divider(height: 1, thickness: 0.5, color: OmiColors.border, indent: 56, endIndent: 16),
      ],
    );
  }
}
