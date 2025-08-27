import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/pages/apps/widgets/popular_apps_section.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import 'widgets/create_options_sheet.dart';

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

  // Cache grouped apps to avoid recomputing on every rebuild
  Map<String, List<App>>? _cachedGroupedApps;
  List<App>? _cachedAllApps;

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

  Map<String, List<App>> _groupAppsByCategory(List<App> apps) {
    // Use cached result if apps haven't changed
    if (_cachedAllApps != null && _cachedGroupedApps != null && apps.length == _cachedAllApps!.length) {
      return _cachedGroupedApps!;
    }

    Map<String, List<App>> groupedApps = {};
    for (var app in apps) {
      String categoryName = app.getCategoryName();
      if (!groupedApps.containsKey(categoryName)) {
        groupedApps[categoryName] = [];
      }
      groupedApps[categoryName]!.add(app);
    }

    // Cache the result
    _cachedAllApps = List.from(apps);
    _cachedGroupedApps = groupedApps;

    return groupedApps;
  }

  Widget _buildAppsView() {
    return Selector<AppProvider, ({bool isFilterActive, bool isSearchActive})>(
      selector: (context, provider) => (
        isFilterActive: provider.isFilterActive(),
        isSearchActive: provider.isSearchActive(),
      ),
      builder: (context, state, child) {
        if (state.isFilterActive || state.isSearchActive) {
          return _buildFilteredAppsView();
        }
        return _buildCategorizedAppsView();
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
    return CustomScrollView(
      slivers: [
        const SliverToBoxAdapter(child: SizedBox(height: 8)),
        // Shimmer for Popular Apps
        SliverToBoxAdapter(child: _buildShimmerCategorySection()),
        // Shimmer for other categories (show 3-4 category sections)
        SliverToBoxAdapter(child: _buildShimmerCategorySection()),
        SliverToBoxAdapter(child: _buildShimmerCategorySection()),
        SliverToBoxAdapter(child: _buildShimmerCategorySection()),
        const SliverToBoxAdapter(child: SizedBox(height: 100)),
      ],
    );
  }

  Widget _buildFilteredAppsView() {
    return Selector<AppProvider, List<App>>(
      selector: (context, provider) => provider.filteredApps,
      builder: (context, filteredApps, child) {
        return CustomScrollView(
          controller: widget.scrollController,
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 20)),
            if (filteredApps.isEmpty)
              SliverToBoxAdapter(
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
              )
            else
              SliverPadding(
                padding: const EdgeInsets.only(bottom: 64, left: 20, right: 20),
                sliver: SliverList.separated(
                  itemCount: filteredApps.length,
                  itemBuilder: (context, index) {
                    return Selector<AppProvider, List<App>>(
                      selector: (context, provider) => provider.apps,
                      builder: (context, allApps, child) {
                        final originalIndex = allApps.indexWhere(
                          (app) => app.id == filteredApps[index].id,
                        );
                        return AppListItem(
                          app: filteredApps[index],
                          index: originalIndex,
                        );
                      },
                    );
                  },
                  separatorBuilder: (context, index) => const SizedBox(height: 8),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildCategorizedAppsView() {
    return Selector<AppProvider, List<App>>(
      selector: (context, provider) => provider.apps,
      builder: (context, apps, child) {
        final groupedApps = _groupAppsByCategory(apps);

        // Get most downloaded apps overall (sorted by installs)
        final allApps = List<App>.from(apps);
        allApps.sort((a, b) => b.installs.compareTo(a.installs));
        final mostDownloadedApps = allApps.take(20).toList(); // Get top 20 most downloaded

        return CustomScrollView(
          controller: widget.scrollController,
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 8)),

            // Popular Apps Section - First category, no view all
            if (mostDownloadedApps.isNotEmpty)
              SliverToBoxAdapter(
                child: CategorySection(
                  categoryName: 'Popular Apps',
                  apps: mostDownloadedApps,
                  showViewAll: false,
                  onViewAll: () {}, // Not used since showViewAll is false
                ),
              ),

            // Other categories sections - sorted alphabetically
            ...(() {
              final sortedEntries = groupedApps.entries.where((entry) => entry.key != 'Popular').toList();

              // Custom sorting: alphabetical but with blank/empty and "Other" at the end
              sortedEntries.sort((a, b) {
                final aKey = a.key.trim();
                final bKey = b.key.trim();

                // Handle blank/empty categories
                if (aKey.isEmpty && bKey.isEmpty) return 0;
                if (aKey.isEmpty) return 1; // a goes to end
                if (bKey.isEmpty) return -1; // b goes to end

                // Handle "Other" category
                if (aKey.toLowerCase() == 'other' && bKey.toLowerCase() == 'other') return 0;
                if (aKey.toLowerCase() == 'other') return 1; // a goes to end
                if (bKey.toLowerCase() == 'other') return -1; // b goes to end

                // Normal alphabetical sorting
                return aKey.compareTo(bKey);
              });

              return sortedEntries;
            })()
                .map((entry) {
              final categoryName = entry.key;
              final categoryApps = entry.value;

              return SliverToBoxAdapter(
                child: CategorySection(
                  categoryName: categoryName,
                  apps: categoryApps,
                  onViewAll: () {
                    final category = context.read<AddAppProvider>().categories.firstWhere(
                          (cat) => cat.title == categoryName,
                          orElse: () =>
                              Category(title: categoryName, id: categoryName.toLowerCase().replaceAll(' ', '-')),
                        );
                    routeToPage(
                      context,
                      CategoryAppsPage(
                        category: category,
                        apps: categoryApps,
                      ),
                    );
                  },
                ),
              );
            }),

            const SliverToBoxAdapter(child: SizedBox(height: 100)),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    // Wrap with NotificationListener to catch SelectAppNotification
    super.build(context);
    return NotificationListener<SelectAppNotification>(
        onNotification: _handleSelectAppNotification,
        child: Selector<AppProvider,
            ({bool isLoading, Map<String, dynamic> filters, bool isSearchActive, int filterCount})>(
          selector: (context, provider) => (
            isLoading: provider.isLoading,
            filters: provider.filters,
            isSearchActive: provider.isSearchActive(),
            filterCount: provider.filters.length
          ),
          builder: (context, state, child) {
            return CustomScrollView(
              controller: widget.scrollController,
              slivers: [
                const SliverToBoxAdapter(child: SizedBox(height: 12)),
                SliverToBoxAdapter(
                  child: state.isLoading
                      ? _buildShimmerCreateButton()
                      : GestureDetector(
                          onTap: () async {
                            showModalBottomSheet(
                              context: context,
                              builder: (context) => const CreateOptionsSheet(),
                              shape: const RoundedRectangleBorder(
                                borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                              ),
                            );
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
                          margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: Column(
                                  children: [
                                    SizedBox(
                                      height: 44,
                                      child: SearchBar(
                                        hintText: 'Search Apps',
                                        leading: const Padding(
                                          padding: EdgeInsets.only(left: 6.0),
                                          child:
                                              Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white70, size: 14),
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
                                    if (state.filterCount > 0) ...[
                                      const SizedBox(height: 8),
                                      SizedBox(
                                        height: 32,
                                        child: ListView.separated(
                                          scrollDirection: Axis.horizontal,
                                          itemBuilder: (ctx, idx) {
                                            return Container(
                                              height: 32,
                                              decoration: BoxDecoration(
                                                color: AppStyles.backgroundSecondary,
                                                borderRadius: BorderRadius.circular(16),
                                              ),
                                              child: TextButton.icon(
                                                onPressed: () {
                                                  context
                                                      .read<AppProvider>()
                                                      .removeFilter(state.filters.keys.elementAt(idx));
                                                },
                                                icon: const Icon(
                                                  Icons.close,
                                                  size: 12,
                                                  color: Colors.white70,
                                                ),
                                                label: Text(
                                                  filterValueToString(state.filters.values.elementAt(idx)),
                                                  style: const TextStyle(
                                                    fontSize: 12,
                                                    color: Colors.white,
                                                  ),
                                                ),
                                                style: TextButton.styleFrom(
                                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                                                  minimumSize: Size.zero,
                                                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                                ),
                                              ),
                                            );
                                          },
                                          separatorBuilder: (ctx, idx) => const SizedBox(width: 8),
                                          itemCount: state.filterCount,
                                        ),
                                      ),
                                    ],
                                  ],
                                ),
                              ),

                              const SizedBox(width: 8),

                              // Filter button
                              SizedBox(
                                width: 44,
                                height: 44,
                                child: Container(
                                  decoration: BoxDecoration(
                                    color: AppStyles.backgroundSecondary,
                                    borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                  ),
                                  child: IconButton(
                                    onPressed: () {
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
                              ),
                            ],
                          ),
                        ),
                ),

                const SliverToBoxAdapter(child: SizedBox(height: 0)),

                // Main content - show shimmer when loading
                SliverFillRemaining(
                  child: state.isLoading ? _buildShimmerAppsView() : _buildAppsView(),
                ),
              ],
            );
          },
        ));
  }

  @override
  bool get wantKeepAlive => true;
}
