import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/widgets/popular_apps_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';

String filterValueToString(dynamic value) {
  if (value is String) {
    return value;
  } else if (value is Category) {
    return value.title;
  } else if (value is AppCapability) {
    return value.title;
  }
  return value.toString();
}

class ExploreInstallPage extends StatefulWidget {
  final ScrollController? scrollController;
  const ExploreInstallPage({super.key, this.scrollController});

  @override
  State<ExploreInstallPage> createState() => ExploreInstallPageState();
}

class ExploreInstallPageState extends State<ExploreInstallPage> with AutomaticKeepAliveClientMixin {
  // ValueNotifier to hold the selected app
  final ValueNotifier<App?> _selectedAppNotifier = ValueNotifier<App?>(null);
  late TextEditingController searchController;
  Debouncer debouncer = Debouncer(delay: const Duration(milliseconds: 500));

  @override
  void initState() {
    searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().init();
    });
    super.initState();
  }

  // Handle SelectAppNotification from child widgets
  bool _handleSelectAppNotification(SelectAppNotification notification) {
    _selectedAppNotifier.value = notification.app;

    routeToPage(context, AppDetailPage(app: notification.app));

    return true;
  }

  void scrollToTop() {
    if (widget.scrollController != null && widget.scrollController!.hasClients) {
      widget.scrollController!.animateTo(0.0, duration: const Duration(milliseconds: 500), curve: Curves.easeOutCubic);
    }
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  Widget _buildFilteredAppsSlivers() {
    return Selector<AppProvider, List<App>>(
      selector: (context, provider) => provider.filteredApps,
      builder: (context, filteredApps, child) {
        if (filteredApps.isEmpty) {
          return SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.3),
              child: Column(
                children: [
                  Icon(Icons.search_off, size: 64, color: Colors.grey.shade600),
                  const SizedBox(height: 16),
                  Text(
                    context.l10n.noAppsFound,
                    style: const TextStyle(fontSize: 18, color: Colors.white70),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.tryAdjustingSearch,
                    style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          );
        }

        return SliverPadding(
          padding: const EdgeInsets.only(bottom: 64, left: 20, right: 20, top: 20),
          sliver: SliverList.separated(
            itemCount: filteredApps.length,
            separatorBuilder: (context, index) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final app = filteredApps[index];
              return Selector<AppProvider, List<App>>(
                selector: (context, provider) => provider.apps,
                builder: (context, allApps, child) {
                  final originalIndex = allApps.indexWhere((appItem) => appItem.id == app.id);
                  return AppListItem(app: app, index: originalIndex);
                },
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildCategorizedAppsSlivers() {
    // Render v2 groups directly from provider (grouped by capability)
    return Selector<AppProvider, List<Map<String, dynamic>>>(
      selector: (context, provider) => provider.groupedApps,
      builder: (context, groups, child) {
        // Filter out sections that are accessed elsewhere:
        // - "Summary" (memories) section - accessed via conversation detail page
        // - "Chat Assistants" (chat) section - accessed via chat page drawer
        final filteredGroups = groups.where((group) {
          final capabilityMap = group['capability'] as Map<String, dynamic>?;
          final groupId = capabilityMap?['id'] as String? ?? '';
          return groupId != 'memories' && groupId != 'chat';
        }).toList();

        return SliverPadding(
          padding: const EdgeInsets.only(top: 8, bottom: 100),
          sliver: SliverList.builder(
            itemCount: filteredGroups.length,
            itemBuilder: (context, index) {
              final group = filteredGroups[index];
              // Support capability-based grouping (new) and category-based (legacy)
              final capabilityMap = group['capability'] as Map<String, dynamic>?;
              final categoryMap = group['category'] as Map<String, dynamic>?;

              final groupMap = capabilityMap ?? categoryMap;
              final groupTitle = (groupMap != null ? (groupMap['title'] as String? ?? '') : '').trim();
              final groupId = groupMap != null ? (groupMap['id'] as String? ?? '') : '';
              final groupApps = group['data'] as List<App>? ?? <App>[];

              // Get localized section title
              String localizedSectionTitle;
              if (capabilityMap != null) {
                final capability = AppCapability(
                  title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                  id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '_') : groupId,
                );
                localizedSectionTitle = capability.getLocalizedTitle(context);
              } else {
                final category = context.read<AddAppProvider>().categories.firstWhere(
                      (cat) => cat.id == groupId || cat.title == groupTitle,
                      orElse: () => Category(
                        title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                        id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '-') : groupId,
                      ),
                    );
                localizedSectionTitle = category.getLocalizedTitle(context);
              }

              return CategorySection(
                categoryName: localizedSectionTitle,
                apps: groupApps,
                showViewAll: groupApps.length > 9,
                onViewAll: () {
                  if (capabilityMap != null) {
                    // Capability-based navigation - use title from grouped response to match section title
                    final capability = AppCapability(
                      title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                      id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '_') : groupId,
                    );
                    routeToPage(context, CapabilityAppsPage(capability: capability, apps: groupApps));
                  } else {
                    // Legacy category-based navigation
                    final category = context.read<AddAppProvider>().categories.firstWhere(
                          (cat) => cat.id == groupId || cat.title == groupTitle,
                          orElse: () => Category(
                            title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                            id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '-') : groupId,
                          ),
                        );
                    routeToPage(context, CategoryAppsPage(category: category, apps: groupApps));
                  }
                },
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildShimmerSearchBar() {
    return ShimmerWithTimeout(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Row(
          children: [
            Expanded(
              child: Container(
                height: 48,
                decoration: BoxDecoration(
                  color: AppStyles.backgroundSecondary,
                  borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 44,
              height: 48,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerCategorySection() {
    return ShimmerWithTimeout(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        margin: const EdgeInsets.only(top: 12, bottom: 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Category title shimmer
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
              child: Row(
                children: [
                  Container(
                    width: 140,
                    height: 20,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundSecondary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const Spacer(),
                  Container(
                    width: 60,
                    height: 20,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundSecondary,
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ],
              ),
            ),
            // Apps grid shimmer
            Container(
              height: 270, // Approximate height for 3 rows
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: GridView.builder(
                scrollDirection: Axis.horizontal,
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 3,
                  childAspectRatio: 0.28,
                  crossAxisSpacing: 0.0,
                  mainAxisSpacing: 14.0,
                ),
                itemCount: 9, // Show 9 shimmer items
                itemBuilder: (context, index) => Container(
                  padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 4.0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Container(
                        width: 60,
                        height: 60,
                        decoration: BoxDecoration(
                          color: AppStyles.backgroundSecondary,
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: double.infinity,
                              height: 16,
                              decoration: BoxDecoration(
                                color: AppStyles.backgroundSecondary,
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                            const SizedBox(height: 4),
                            Container(
                              width: 80,
                              height: 12,
                              decoration: BoxDecoration(
                                color: AppStyles.backgroundSecondary,
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        width: 60,
                        height: 28,
                        decoration: BoxDecoration(
                          color: AppStyles.backgroundSecondary,
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerAppsView() {
    return Column(
      children: [
        const SizedBox(height: 8),
        // Shimmer for Popular Apps
        _buildShimmerCategorySection(),
        // Shimmer for other categories (show 3-4 category sections)
        _buildShimmerCategorySection(),
        _buildShimmerCategorySection(),
        _buildShimmerCategorySection(),
        const SizedBox(height: 100),
      ],
    );
  }

  Widget _buildSearchLoadingSliver() {
    return SliverPadding(
      padding: const EdgeInsets.only(bottom: 64, left: 20, right: 20, top: 20),
      sliver: SliverList(
        delegate: SliverChildBuilderDelegate(
          (context, index) => _buildShimmerListItem(),
          childCount: 5, // Show 5 shimmer items
        ),
      ),
    );
  }

  Widget _buildShimmerListItem() {
    return ShimmerWithTimeout(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(color: AppStyles.backgroundSecondary, borderRadius: BorderRadius.circular(16)),
        child: Row(
          children: [
            // App icon shimmer
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(color: AppStyles.backgroundTertiary, borderRadius: BorderRadius.circular(12)),
            ),
            const SizedBox(width: 16),
            // App info shimmer
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: double.infinity,
                    height: 18,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    width: 150,
                    height: 14,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            // Button shimmer
            Container(
              width: 72,
              height: 32,
              decoration: BoxDecoration(color: AppStyles.backgroundTertiary, borderRadius: BorderRadius.circular(16)),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Wrap with NotificationListener to catch SelectAppNotification
    super.build(context);
    return NotificationListener<SelectAppNotification>(
      onNotification: _handleSelectAppNotification,
      child: Selector<
          AppProvider,
          ({
            bool isLoading,
            bool isSearching,
            Map<String, dynamic> filters,
            bool isSearchActive,
            bool isFilterActive,
            int filterCount,
            bool isMyAppsSelected,
            bool isInstalledSelected,
            int visibleFilterCount,
            String? firstFilterText,
          })>(
        selector: (context, provider) {
          // Calculate visible filters (excluding "My Apps" and "Installed Apps")
          final visibleFilters = provider.filters.entries.where((entry) {
            if (entry.key == 'Apps') {
              return entry.value != 'My Apps' && entry.value != 'Installed Apps';
            }
            return true;
          }).toList();

          return (
            isLoading: provider.isLoading,
            isSearching: provider.isSearching,
            filters: provider.filters,
            isSearchActive: provider.isSearchActive(),
            isFilterActive: provider.isFilterActive(),
            filterCount: provider.filters.length,
            isMyAppsSelected: provider.isFilterSelected('My Apps', 'Apps'),
            isInstalledSelected: provider.isFilterSelected('Installed Apps', 'Apps'),
            visibleFilterCount: visibleFilters.length,
            firstFilterText: visibleFilters.isNotEmpty ? filterValueToString(visibleFilters.first.value) : null,
          );
        },
        builder: (context, state, child) {
          return RefreshIndicator(
            onRefresh: () async {
              HapticFeedback.mediumImpact();
              await context.read<AppProvider>().forceRefreshApps();
            },
            color: Colors.deepPurpleAccent,
            backgroundColor: Colors.white,
            child: CustomScrollView(
              controller: widget.scrollController,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                const SliverToBoxAdapter(child: SizedBox(height: 4)),

                // Top bar: search plus a single overflow menu - shimmer when loading
                SliverToBoxAdapter(
                  child: state.isLoading
                      ? _buildShimmerSearchBar()
                      : Container(
                          margin: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                          child: Row(
                            children: [
                              // Search keeps full width now that My Apps,
                              // Installed and Filters live in the menu beside it.
                              Expanded(
                                child: SizedBox(
                                  height: 44,
                                  child: SearchBar(
                                    hintText: context.l10n.searchAppsPlaceholder,
                                    leading: const Padding(
                                      padding: EdgeInsets.only(left: 6.0),
                                      child: Icon(Icons.search, color: Colors.white60, size: 20),
                                    ),
                                    backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
                                    elevation: WidgetStateProperty.all(0),
                                    padding: WidgetStateProperty.all(
                                      const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                    ),
                                    focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
                                    controller: searchController,
                                    trailing: state.isSearchActive
                                        ? [
                                            IconButton(
                                              icon: const Icon(Icons.close, color: Colors.white70, size: 16),
                                              padding: EdgeInsets.zero,
                                              constraints: const BoxConstraints(minHeight: 36, minWidth: 36),
                                              onPressed: () {
                                                searchController.clear();
                                                context.read<AppProvider>().searchApps('');
                                              },
                                            ),
                                          ]
                                        : null,
                                    hintStyle: WidgetStateProperty.all(
                                      TextStyle(color: AppStyles.textTertiary, fontSize: 14),
                                    ),
                                    textStyle: WidgetStateProperty.all(
                                      const TextStyle(color: AppStyles.textPrimary, fontSize: 14),
                                    ),
                                    shape: WidgetStateProperty.all(
                                      RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                      ),
                                    ),
                                    onChanged: (value) {
                                      debouncer.run(() {
                                        context.read<AppProvider>().searchApps(value);
                                      });
                                    },
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              _AppsOverflowMenu(
                                isMyAppsSelected: state.isMyAppsSelected,
                                isInstalledSelected: state.isInstalledSelected,
                                visibleFilterCount: state.visibleFilterCount,
                              ),
                            ],
                          ),
                        ),
                ),

                const SliverToBoxAdapter(child: SizedBox(height: 0)),

                // Main content - show shimmer when loading
                if (state.isLoading)
                  SliverToBoxAdapter(child: _buildShimmerAppsView())
                else if (state.isSearching)
                  _buildSearchLoadingSliver()
                else if (state.isFilterActive || state.isSearchActive)
                  _buildFilteredAppsSlivers()
                else
                  _buildCategorizedAppsSlivers(),
              ],
            ),
          );
        },
      ),
    );
  }

  @override
  bool get wantKeepAlive => true;
}

/// Single menu beside the search bar. Collapses what used to be three inline
/// buttons (My Apps, Installed, Filters) plus the app-bar create menu.
class _AppsOverflowMenu extends StatelessWidget {
  final bool isMyAppsSelected;
  final bool isInstalledSelected;
  final int visibleFilterCount;

  const _AppsOverflowMenu({
    required this.isMyAppsSelected,
    required this.isInstalledSelected,
    required this.visibleFilterCount,
  });

  void _toggleFilter(BuildContext context, String value) {
    HapticFeedback.mediumImpact();
    final provider = context.read<AppProvider>();
    final wasSelected = provider.isFilterSelected(value, 'Apps');
    provider.addOrRemoveFilter(value, 'Apps');
    provider.applyFilters();
    PlatformManager.instance.analytics.appsTypeFilter(value, !wasSelected);
  }

  void _openFilterSheet(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (context) => const FilterBottomSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    // The inline buttons used to show their own active state; with everything
    // behind one button the badge is the only remaining signal that a filter
    // is narrowing the list.
    final activeCount = visibleFilterCount + (isMyAppsSelected ? 1 : 0) + (isInstalledSelected ? 1 : 0);

    return PullDownButton(
      itemBuilder: (context) => [
        PullDownMenuItem.selectable(
          title: context.l10n.myApps,
          selected: isMyAppsSelected,
          iconWidget: const FaIcon(FontAwesomeIcons.solidUser, size: 16),
          onTap: () => _toggleFilter(context, 'My Apps'),
        ),
        PullDownMenuItem.selectable(
          title: context.l10n.installedApps,
          selected: isInstalledSelected,
          iconWidget: const FaIcon(FontAwesomeIcons.download, size: 16),
          onTap: () => _toggleFilter(context, 'Installed Apps'),
        ),
        const PullDownMenuDivider.large(),
        PullDownMenuItem(
          title: context.l10n.filters,
          subtitle: visibleFilterCount > 0 ? '$visibleFilterCount' : null,
          iconWidget: const FaIcon(FontAwesomeIcons.filter, size: 16),
          onTap: () => _openFilterSheet(context),
        ),
        const PullDownMenuDivider.large(),
        PullDownMenuItem(
          title: context.l10n.createAnApp,
          subtitle: context.l10n.createAndShareYourApp,
          iconWidget: const Icon(Icons.apps, size: 18),
          onTap: () {
            PlatformManager.instance.analytics.pageOpened('Submit App');
            routeToPage(context, const AddAppPage());
          },
        ),
        PullDownMenuItem(
          title: context.l10n.addMcpServer,
          subtitle: context.l10n.connectExternalAiTools,
          iconWidget: const Icon(Icons.cable, size: 18),
          onTap: () {
            PlatformManager.instance.analytics.pageOpened('Add MCP Server');
            routeToPage(context, const AddMcpServerPage());
          },
        ),
      ],
      buttonBuilder: (context, showMenu) => GestureDetector(
        onTap: () {
          HapticFeedback.mediumImpact();
          showMenu();
        },
        child: SizedBox(
          width: 44,
          height: 44,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              // Sized explicitly: a non-positioned Stack child gets loose
              // constraints, so without this the pill shrinks to the icon.
              Container(
                width: 44,
                height: 44,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppStyles.backgroundSecondary,
                  borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                ),
                child: const Icon(Icons.more_horiz, size: 20, color: Colors.white),
              ),
              if (activeCount > 0)
                Positioned(
                  top: -4,
                  right: -4,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      border: Border.all(color: Colors.black, width: 1.5),
                    ),
                    constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                    child: Center(
                      child: Text(
                        '$activeCount',
                        style: const TextStyle(
                          color: Colors.black,
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          height: 1.0,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
