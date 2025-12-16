import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/widgets/popular_apps_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import 'add_app.dart';

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
      widget.scrollController!.animateTo(
        0.0,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOutCubic,
      );
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
                  Icon(
                    Icons.search_off,
                    size: 64,
                    color: Colors.grey.shade600,
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'No apps found',
                    style: TextStyle(fontSize: 18, color: Colors.white70),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Try adjusting your search or filters',
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
                  final originalIndex = allApps.indexWhere(
                    (appItem) => appItem.id == app.id,
                  );
                  return AppListItem(
                    app: app,
                    index: originalIndex,
                  );
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
        // Filter out "Summary" (memories) section - it's accessed via conversation detail page
        final filteredGroups = groups.where((group) {
          final capabilityMap = group['capability'] as Map<String, dynamic>?;
          final groupId = capabilityMap?['id'] as String? ?? '';
          return groupId != 'memories';
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

              return CategorySection(
                categoryName: groupTitle.isEmpty ? 'Apps' : groupTitle,
                apps: groupApps,
                showViewAll: groupApps.length > 9,
                onViewAll: () {
                  if (capabilityMap != null) {
                    // Capability-based navigation - use title from grouped response to match section title
                    final capability = AppCapability(
                      title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                      id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '_') : groupId,
                    );
                    routeToPage(
                      context,
                      CapabilityAppsPage(
                        capability: capability,
                        apps: groupApps,
                      ),
                    );
                  } else {
                    // Legacy category-based navigation
                    final category = context.read<AddAppProvider>().categories.firstWhere(
                          (cat) => cat.id == groupId || cat.title == groupTitle,
                          orElse: () => Category(
                            title: groupTitle.isEmpty ? 'Apps' : groupTitle,
                            id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '-') : groupId,
                          ),
                        );
                    routeToPage(
                      context,
                      CategoryAppsPage(
                        category: category,
                        apps: groupApps,
                      ),
                    );
                  }
                },
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildShimmerCreateButton() {
    return Shimmer.fromColors(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        padding: const EdgeInsets.all(20),
        margin: const EdgeInsets.fromLTRB(16, 16, 16, 16),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: AppStyles.backgroundTertiary,
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 180,
                    height: 16,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Container(
                    width: 120,
                    height: 12,
                    decoration: BoxDecoration(
                      color: AppStyles.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ],
              ),
            ),
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                color: AppStyles.backgroundTertiary,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerSearchBar() {
    return Shimmer.fromColors(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Row(
          children: [
            Expanded(
              child: Container(
                height: 44,
                decoration: BoxDecoration(
                  color: AppStyles.backgroundSecondary,
                  borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                ),
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
    return Shimmer.fromColors(
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
    return Shimmer.fromColors(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            // App icon shimmer
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                color: AppStyles.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
              ),
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
              decoration: BoxDecoration(
                color: AppStyles.backgroundTertiary,
                borderRadius: BorderRadius.circular(16),
              ),
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
                  SliverToBoxAdapter(
                    child: state.isLoading
                        ? _buildShimmerCreateButton()
                        : GestureDetector(
                            onTap: () {
                              MixpanelManager().pageOpened('Submit App');
                              routeToPage(context, const AddAppPage());
                            },
                            child: Container(
                              padding: const EdgeInsets.all(20),
                              margin: const EdgeInsets.fromLTRB(16, 16, 16, 16),
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
                                      Icons.add,
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
                                          'Create Your Own App',
                                          style: TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                            color: Colors.black,
                                          ),
                                        ),
                                        SizedBox(height: 2),
                                        Text(
                                          'Build and share your custom app',
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
                          ),
                  ),

                  // Top bar with search and filters - show shimmer when loading
                  SliverToBoxAdapter(
                    child: state.isLoading
                        ? _buildShimmerSearchBar()
                        : Container(
                            margin: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Search bar - shrinks to square when filters are active (but not when search is active)
                                AnimatedContainer(
                                  duration: const Duration(milliseconds: 200),
                                  curve: Curves.easeInOut,
                                  width: (!state.isSearchActive &&
                                          (state.isMyAppsSelected ||
                                              state.isInstalledSelected ||
                                              state.visibleFilterCount > 0))
                                      ? 44
                                      : null,
                                  child: (!state.isSearchActive &&
                                          (state.isMyAppsSelected ||
                                              state.isInstalledSelected ||
                                              state.visibleFilterCount > 0))
                                      ? SizedBox(
                                          height: 44,
                                          child: Container(
                                            decoration: BoxDecoration(
                                              color: AppStyles.backgroundSecondary,
                                              borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                            ),
                                            child: IconButton(
                                              onPressed: () {
                                                // Clear all filters and expand search
                                                final provider = context.read<AppProvider>();
                                                if (state.isMyAppsSelected) {
                                                  provider.addOrRemoveFilter('My Apps', 'Apps');
                                                }
                                                if (state.isInstalledSelected) {
                                                  provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                                }
                                                // Clear other filters
                                                final visibleFilters = state.filters.entries.where((entry) {
                                                  if (entry.key == 'Apps') {
                                                    return entry.value != 'My Apps' && entry.value != 'Installed Apps';
                                                  }
                                                  return true;
                                                }).toList();
                                                for (final entry in visibleFilters) {
                                                  provider.removeFilter(entry.key);
                                                }
                                                provider.applyFilters();
                                              },
                                              icon: const Icon(
                                                FontAwesomeIcons.magnifyingGlass,
                                                color: Colors.white70,
                                                size: 14,
                                              ),
                                              padding: EdgeInsets.zero,
                                            ),
                                          ),
                                        )
                                      : Expanded(
                                          child: Column(
                                            children: [
                                              SizedBox(
                                                height: 44,
                                                child: SearchBar(
                                                  hintText: 'Search 1500+ Apps',
                                                  leading: const Padding(
                                                    padding: EdgeInsets.only(left: 6.0),
                                                    child: Icon(FontAwesomeIcons.magnifyingGlass,
                                                        color: Colors.white70, size: 14),
                                                  ),
                                                  backgroundColor:
                                                      WidgetStateProperty.all(AppStyles.backgroundSecondary),
                                                  elevation: WidgetStateProperty.all(0),
                                                  padding: WidgetStateProperty.all(
                                                    const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                                  ),
                                                  focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
                                                  controller: searchController,
                                                  trailing: state.isSearchActive
                                                      ? [
                                                          IconButton(
                                                            icon: const Icon(Icons.close,
                                                                color: Colors.white70, size: 16),
                                                            padding: EdgeInsets.zero,
                                                            constraints: const BoxConstraints(
                                                              minHeight: 36,
                                                              minWidth: 36,
                                                            ),
                                                            onPressed: () {
                                                              searchController.clear();
                                                              context.read<AppProvider>().searchApps('');
                                                            },
                                                          )
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
                                            ],
                                          ),
                                        ),
                                ),

                                const SizedBox(width: 8),

                                // My Apps button - expands when selected
                                state.isMyAppsSelected
                                    ? Expanded(
                                        child: AnimatedContainer(
                                          duration: const Duration(milliseconds: 200),
                                          curve: Curves.easeInOut,
                                          height: 44,
                                          decoration: BoxDecoration(
                                            color: Colors.deepPurpleAccent.withValues(alpha: 0.5),
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                          child: TextButton.icon(
                                            onPressed: () {
                                              HapticFeedback.mediumImpact();
                                              final provider = context.read<AppProvider>();
                                              final wasSelected = provider.isFilterSelected('My Apps', 'Apps');
                                              provider.addOrRemoveFilter('My Apps', 'Apps');
                                              provider.applyFilters();
                                              MixpanelManager().appsTypeFilter('My Apps', !wasSelected);
                                            },
                                            icon: const FaIcon(
                                              FontAwesomeIcons.solidUser,
                                              size: 16,
                                              color: Colors.white,
                                            ),
                                            label: const Text(
                                              'My Apps',
                                              style: TextStyle(
                                                fontSize: 14,
                                                color: Colors.white,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                            style: TextButton.styleFrom(
                                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            ),
                                          ),
                                        ),
                                      )
                                    : SizedBox(
                                        width: 44,
                                        height: 44,
                                        child: AnimatedContainer(
                                          duration: const Duration(milliseconds: 200),
                                          curve: Curves.easeInOut,
                                          decoration: BoxDecoration(
                                            color: AppStyles.backgroundSecondary,
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                          child: IconButton(
                                            onPressed: () {
                                              HapticFeedback.mediumImpact();
                                              final provider = context.read<AppProvider>();
                                              final wasSelected = provider.isFilterSelected('My Apps', 'Apps');
                                              provider.addOrRemoveFilter('My Apps', 'Apps');
                                              provider.applyFilters();
                                              MixpanelManager().appsTypeFilter('My Apps', !wasSelected);
                                            },
                                            icon: const FaIcon(
                                              FontAwesomeIcons.solidUser,
                                              size: 16,
                                              color: Colors.white,
                                            ),
                                            padding: EdgeInsets.zero,
                                          ),
                                        ),
                                      ),

                                const SizedBox(width: 8),

                                // Installed Apps button - expands when selected
                                state.isInstalledSelected
                                    ? Expanded(
                                        child: AnimatedContainer(
                                          duration: const Duration(milliseconds: 200),
                                          curve: Curves.easeInOut,
                                          height: 44,
                                          decoration: BoxDecoration(
                                            color: Colors.deepPurpleAccent.withValues(alpha: 0.5),
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                          child: TextButton.icon(
                                            onPressed: () {
                                              HapticFeedback.mediumImpact();
                                              final provider = context.read<AppProvider>();
                                              final wasSelected = provider.isFilterSelected('Installed Apps', 'Apps');
                                              provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                              provider.applyFilters();
                                              MixpanelManager().appsTypeFilter('Installed Apps', !wasSelected);
                                            },
                                            icon: const FaIcon(
                                              FontAwesomeIcons.download,
                                              size: 16,
                                              color: Colors.white,
                                            ),
                                            label: Text(
                                              (state.visibleFilterCount > 0 && !state.isSearchActive)
                                                  ? 'Installed'
                                                  : 'Installed Apps',
                                              style: const TextStyle(
                                                fontSize: 14,
                                                color: Colors.white,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                            style: TextButton.styleFrom(
                                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            ),
                                          ),
                                        ),
                                      )
                                    : SizedBox(
                                        width: 44,
                                        height: 44,
                                        child: AnimatedContainer(
                                          duration: const Duration(milliseconds: 200),
                                          curve: Curves.easeInOut,
                                          decoration: BoxDecoration(
                                            color: AppStyles.backgroundSecondary,
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                          child: IconButton(
                                            onPressed: () {
                                              HapticFeedback.mediumImpact();
                                              final provider = context.read<AppProvider>();
                                              final wasSelected = provider.isFilterSelected('Installed Apps', 'Apps');
                                              provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                              provider.applyFilters();
                                              MixpanelManager().appsTypeFilter('Installed Apps', !wasSelected);
                                            },
                                            icon: const FaIcon(
                                              FontAwesomeIcons.download,
                                              size: 16,
                                              color: Colors.white,
                                            ),
                                            padding: EdgeInsets.zero,
                                          ),
                                        ),
                                      ),

                                const SizedBox(width: 8),

                                // Filter button - expands when filters are active (but not when search is active)
                                state.visibleFilterCount > 0 && !state.isSearchActive
                                    ? Expanded(
                                        child: AnimatedContainer(
                                          duration: const Duration(milliseconds: 200),
                                          curve: Curves.easeInOut,
                                          height: 44,
                                          decoration: BoxDecoration(
                                            color: Colors.deepPurpleAccent.withValues(alpha: 0.5),
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                          child: TextButton.icon(
                                            onPressed: () {
                                              HapticFeedback.mediumImpact();
                                              showModalBottomSheet(
                                                context: context,
                                                isScrollControlled: true,
                                                shape: const RoundedRectangleBorder(
                                                  borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                                ),
                                                builder: (context) => const FilterBottomSheet(),
                                              );
                                            },
                                            icon: const Icon(
                                              FontAwesomeIcons.filter,
                                              size: 16,
                                              color: Colors.white,
                                            ),
                                            label: const Text(
                                              'Filters',
                                              style: TextStyle(
                                                fontSize: 14,
                                                color: Colors.white,
                                                fontWeight: FontWeight.w500,
                                              ),
                                            ),
                                            style: TextButton.styleFrom(
                                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            ),
                                          ),
                                        ),
                                      )
                                    : SizedBox(
                                        width: 44,
                                        height: 44,
                                        child: Stack(
                                          clipBehavior: Clip.none,
                                          children: [
                                            AnimatedContainer(
                                              duration: const Duration(milliseconds: 200),
                                              curve: Curves.easeInOut,
                                              decoration: BoxDecoration(
                                                color: state.visibleFilterCount > 0
                                                    ? Colors.deepPurpleAccent.withValues(alpha: 0.5)
                                                    : AppStyles.backgroundSecondary,
                                                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                              ),
                                              child: IconButton(
                                                onPressed: () {
                                                  HapticFeedback.mediumImpact();
                                                  showModalBottomSheet(
                                                    context: context,
                                                    isScrollControlled: true,
                                                    shape: const RoundedRectangleBorder(
                                                      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                                    ),
                                                    builder: (context) => const FilterBottomSheet(),
                                                  );
                                                },
                                                icon: const Icon(
                                                  FontAwesomeIcons.filter,
                                                  size: 16,
                                                  color: Colors.white,
                                                ),
                                                padding: EdgeInsets.zero,
                                              ),
                                            ),
                                            // Badge showing filter count when filters are active
                                            if (state.visibleFilterCount > 0)
                                              Positioned(
                                                top: -4,
                                                right: -4,
                                                child: Container(
                                                  padding: const EdgeInsets.all(4),
                                                  decoration: BoxDecoration(
                                                    color: Colors.white,
                                                    shape: BoxShape.circle,
                                                    border: Border.all(
                                                      color: Colors.black,
                                                      width: 1.5,
                                                    ),
                                                  ),
                                                  constraints: const BoxConstraints(
                                                    minWidth: 16,
                                                    minHeight: 16,
                                                  ),
                                                  child: Center(
                                                    child: Text(
                                                      state.visibleFilterCount.toString(),
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
        ));
  }

  @override
  bool get wantKeepAlive => true;
}
