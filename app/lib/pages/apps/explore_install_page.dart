import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/widgets/popular_apps_section.dart';
import 'package:omi/pages/apps/widgets/search_loading_sliver.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';

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
          return SliverPadding(
            padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.3),
            sliver: SliverToBoxAdapter(
              child: OmiEmptyState(
                icon: Icons.search_off,
                title: context.l10n.noAppsFound,
                message: context.l10n.tryAdjustingSearch,
              ),
            ),
          );
        }

        return SliverPadding(
          padding: EdgeInsets.only(bottom: bottomNavBarClearance(context), left: 20, right: 20, top: 20),
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
          padding: EdgeInsets.only(top: 8, bottom: bottomNavBarClearance(context)),
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

              // Fallback title when the backend sends none: the localized generic "Apps", not the
              // internal group id/title used for provider lookups above.
              final fallbackGroupTitle = groupTitle.isEmpty ? context.l10n.apps : groupTitle;

              // Get localized section title
              String localizedSectionTitle;
              if (capabilityMap != null) {
                final capability = AppCapability(
                  title: fallbackGroupTitle,
                  id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '_') : groupId,
                );
                localizedSectionTitle = capability.getLocalizedTitle(context);
              } else {
                final category = context.read<AddAppProvider>().categories.firstWhere(
                      (cat) => cat.id == groupId || cat.title == groupTitle,
                      orElse: () => Category(
                        title: fallbackGroupTitle,
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
                      title: fallbackGroupTitle,
                      id: groupId.isEmpty ? groupTitle.toLowerCase().replaceAll(' ', '_') : groupId,
                    );
                    routeToPage(context, CapabilityAppsPage(capability: capability, apps: groupApps));
                  } else {
                    // Legacy category-based navigation
                    final category = context.read<AddAppProvider>().categories.firstWhere(
                          (cat) => cat.id == groupId || cat.title == groupTitle,
                          orElse: () => Category(
                            title: fallbackGroupTitle,
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
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface2,
      child: Container(
        margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
        child: Row(
          children: [
            Expanded(
              child: Container(
                height: 48,
                decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
              ),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Container(
              width: 44,
              height: 48,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerCategorySection() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface2,
      child: Container(
        margin: const EdgeInsets.only(top: OmiSpacing.sm, bottom: OmiSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Category title shimmer
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xl, OmiSpacing.lg, OmiSpacing.md),
              child: Row(
                children: [
                  Container(
                    width: 140,
                    height: 20,
                    decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
                  ),
                  const Spacer(),
                  Container(
                    width: 60,
                    height: 20,
                    decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
                  ),
                ],
              ),
            ),
            // Apps grid shimmer
            Container(
              height: 270, // Approximate height for 3 rows
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
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
                  padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs, horizontal: OmiSpacing.xxs),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Container(
                        width: 60,
                        height: 60,
                        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
                      ),
                      const SizedBox(width: OmiSpacing.sm),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: double.infinity,
                              height: 16,
                              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
                            ),
                            const SizedBox(height: OmiSpacing.xxs),
                            Container(
                              width: 80,
                              height: 12,
                              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.smAll),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: OmiSpacing.xs),
                      Container(
                        width: 60,
                        height: 28,
                        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
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
        SizedBox(height: bottomNavBarClearance(context)),
      ],
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
            bool isInstalledSelected,
            int visibleFilterCount,
            String? firstFilterText,
          })>(
        selector: (context, provider) {
          // Installed has its own control; every other filter shows as a chip.
          final visibleFilters = provider.filters.entries.where((entry) {
            if (entry.key == 'Apps') {
              return entry.value != 'Installed Apps';
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
            color: OmiColors.onAccent,
            backgroundColor: OmiColors.accent,
            child: CustomScrollView(
              controller: widget.scrollController,
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                const SliverToBoxAdapter(child: SizedBox(height: 4)),

                // Top bar with search and filters - show shimmer when loading
                SliverToBoxAdapter(
                  child: state.isLoading
                      ? _buildShimmerSearchBar()
                      : Container(
                          margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, 0),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Search bar - shrinks to square when filters are active (but not when search is active)
                              AnimatedContainer(
                                duration: const Duration(milliseconds: 200),
                                curve: Curves.easeInOut,
                                width: (!state.isSearchActive &&
                                        (state.isInstalledSelected || state.visibleFilterCount > 0))
                                    ? kOmiMinTapTarget
                                    : null,
                                child: (!state.isSearchActive &&
                                        (state.isInstalledSelected || state.visibleFilterCount > 0))
                                    ? SizedBox(
                                        height: kOmiMinTapTarget,
                                        child: Container(
                                          decoration: const BoxDecoration(
                                              color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
                                          child: OmiIconButton(
                                            icon: const Icon(Icons.search, size: 20),
                                            color: OmiColors.textSecondary,
                                            label: context.l10n.search,
                                            onPressed: () {
                                              // Clear all filters and expand search
                                              final provider = context.read<AppProvider>();
                                              if (state.isInstalledSelected) {
                                                provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                              }
                                              // Clear other filters
                                              final visibleFilters = state.filters.entries.where((entry) {
                                                if (entry.key == 'Apps') {
                                                  return entry.value != 'Installed Apps';
                                                }
                                                return true;
                                              }).toList();
                                              for (final entry in visibleFilters) {
                                                provider.removeFilter(entry.key);
                                              }
                                              provider.applyFilters();
                                            },
                                          ),
                                        ),
                                      )
                                    : Expanded(
                                        child: Column(
                                          children: [
                                            SizedBox(
                                              height: 44,
                                              child: SearchBar(
                                                hintText: context.l10n.searchAppsPlaceholder,
                                                leading: const Padding(
                                                  padding: EdgeInsets.only(left: OmiSpacing.xs),
                                                  child: Icon(Icons.search, color: OmiColors.textSecondary, size: 20),
                                                ),
                                                backgroundColor: WidgetStateProperty.all(OmiColors.surface1),
                                                elevation: WidgetStateProperty.all(0),
                                                padding: WidgetStateProperty.all(
                                                  const EdgeInsets.symmetric(
                                                      horizontal: OmiSpacing.sm, vertical: OmiSpacing.xxs),
                                                ),
                                                focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
                                                controller: searchController,
                                                trailing: state.isSearchActive
                                                    ? [
                                                        OmiIconButton(
                                                          icon: const Icon(Icons.close, size: 16),
                                                          color: OmiColors.textSecondary,
                                                          label: context.l10n.clearSearch,
                                                          onPressed: () {
                                                            searchController.clear();
                                                            context.read<AppProvider>().searchApps('');
                                                          },
                                                        ),
                                                      ]
                                                    : null,
                                                hintStyle: WidgetStateProperty.all(
                                                  OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                                                ),
                                                textStyle: WidgetStateProperty.all(
                                                  OmiType.subhead.copyWith(color: OmiColors.textPrimary),
                                                ),
                                                shape: WidgetStateProperty.all(
                                                  const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
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

                              // Installed Apps button - expands when selected
                              state.isInstalledSelected
                                  ? Expanded(
                                      child: AnimatedContainer(
                                        duration: const Duration(milliseconds: 200),
                                        curve: Curves.easeInOut,
                                        height: 44,
                                        decoration: BoxDecoration(
                                          color: OmiColors.textPrimary.withValues(alpha: 0.22),
                                          borderRadius: OmiRadius.mdAll,
                                        ),
                                        child: TextButton.icon(
                                          onPressed: () {
                                            HapticFeedback.mediumImpact();
                                            final provider = context.read<AppProvider>();
                                            final wasSelected = provider.isFilterSelected('Installed Apps', 'Apps');
                                            provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                            provider.applyFilters();
                                            PlatformManager.instance.analytics.appsTypeFilter(
                                              'Installed Apps',
                                              !wasSelected,
                                            );
                                          },
                                          icon: const FaIcon(
                                            FontAwesomeIcons.download,
                                            size: 16,
                                            color: OmiColors.textPrimary,
                                          ),
                                          label: Text(
                                            (state.visibleFilterCount > 0 && !state.isSearchActive)
                                                ? context.l10n.installed
                                                : context.l10n.installedApps,
                                            style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                                          ),
                                          style: TextButton.styleFrom(
                                            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 0),
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
                                        decoration: const BoxDecoration(
                                            color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
                                        child: OmiIconButton(
                                          icon: const FaIcon(FontAwesomeIcons.download, size: 16),
                                          label: context.l10n.installedApps,
                                          onPressed: () {
                                            HapticFeedback.mediumImpact();
                                            final provider = context.read<AppProvider>();
                                            final wasSelected = provider.isFilterSelected('Installed Apps', 'Apps');
                                            provider.addOrRemoveFilter('Installed Apps', 'Apps');
                                            provider.applyFilters();
                                            PlatformManager.instance.analytics.appsTypeFilter(
                                              'Installed Apps',
                                              !wasSelected,
                                            );
                                          },
                                        ),
                                      ),
                                    ),

                              const SizedBox(width: OmiSpacing.xs),

                              // Filter button - expands when filters are active (but not when search is active)
                              state.visibleFilterCount > 0 && !state.isSearchActive
                                  ? Expanded(
                                      child: AnimatedContainer(
                                        duration: const Duration(milliseconds: 200),
                                        curve: Curves.easeInOut,
                                        height: 44,
                                        decoration: BoxDecoration(
                                          color: OmiColors.textPrimary.withValues(alpha: 0.22),
                                          borderRadius: OmiRadius.mdAll,
                                        ),
                                        child: TextButton.icon(
                                          onPressed: () {
                                            HapticFeedback.mediumImpact();
                                            FilterBottomSheet.show(context);
                                          },
                                          icon: const FaIcon(
                                            FontAwesomeIcons.filter,
                                            size: 16,
                                            color: OmiColors.textPrimary,
                                          ),
                                          label: Text(
                                            context.l10n.filters,
                                            style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
                                          ),
                                          style: TextButton.styleFrom(
                                            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 0),
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
                                                  ? OmiColors.textPrimary.withValues(alpha: 0.22)
                                                  : OmiColors.surface1,
                                              borderRadius: OmiRadius.mdAll,
                                            ),
                                            child: OmiIconButton(
                                              icon: const FaIcon(FontAwesomeIcons.filter, size: 16),
                                              label: context.l10n.filters,
                                              onPressed: () {
                                                HapticFeedback.mediumImpact();
                                                FilterBottomSheet.show(context);
                                              },
                                            ),
                                          ),
                                          // Badge showing filter count when filters are active
                                          if (state.visibleFilterCount > 0)
                                            Positioned(
                                              top: -4,
                                              right: -4,
                                              child: ExcludeSemantics(
                                                child: Container(
                                                  padding: const EdgeInsets.all(OmiSpacing.xxs),
                                                  decoration: BoxDecoration(
                                                    color: OmiColors.textPrimary,
                                                    shape: BoxShape.circle,
                                                    border: Border.all(color: OmiColors.surface0, width: 1.5),
                                                  ),
                                                  constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                                                  child: Center(
                                                    child: Text(
                                                      state.visibleFilterCount.toString(),
                                                      style: OmiType.caption.copyWith(
                                                        color: OmiColors.onAccent,
                                                        fontWeight: FontWeight.w600,
                                                        height: 1.0,
                                                      ),
                                                      textAlign: TextAlign.center,
                                                    ),
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
                  const SearchLoadingSliver()
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
