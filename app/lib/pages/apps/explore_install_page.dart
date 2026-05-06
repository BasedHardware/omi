import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/apps/widgets/category_apps_page.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/widgets/redesign/app_row_card.dart';
import 'package:omi/pages/apps/widgets/redesign/app_section.dart';
import 'package:omi/pages/apps/widgets/redesign/capability_pills_row.dart';
import 'package:omi/pages/apps/widgets/redesign/segmented_filter.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
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

// Re-exported so existing callers (PopularAppsSection etc.) still compile.
class SelectAppNotification extends Notification {
  final App app;
  SelectAppNotification(this.app);
}

enum _AppsScope { all, connected, mine }

class ExploreInstallPage extends StatefulWidget {
  final ScrollController? scrollController;
  const ExploreInstallPage({super.key, this.scrollController});

  @override
  State<ExploreInstallPage> createState() => ExploreInstallPageState();
}

class ExploreInstallPageState extends State<ExploreInstallPage> with AutomaticKeepAliveClientMixin {
  final ValueNotifier<App?> _selectedAppNotifier = ValueNotifier<App?>(null);
  late TextEditingController searchController;
  Debouncer debouncer = Debouncer(delay: const Duration(milliseconds: 500));

  /// Which capability pill is currently selected (null = show all sections).
  String? _selectedCapabilityId;

  @override
  void initState() {
    searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().init();
    });
    super.initState();
  }

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

  // ----- Scope / filter helpers ---------------------------------------------

  _AppsScope _currentScope(AppProvider provider) {
    if (provider.isFilterSelected('Installed Apps', 'Apps')) return _AppsScope.connected;
    if (provider.isFilterSelected('My Apps', 'Apps')) return _AppsScope.mine;
    return _AppsScope.all;
  }

  void _setScope(_AppsScope scope) {
    final provider = context.read<AppProvider>();
    final myApps = provider.isFilterSelected('My Apps', 'Apps');
    final installed = provider.isFilterSelected('Installed Apps', 'Apps');

    switch (scope) {
      case _AppsScope.all:
        if (myApps) provider.addOrRemoveFilter('My Apps', 'Apps');
        if (installed) provider.addOrRemoveFilter('Installed Apps', 'Apps');
        break;
      case _AppsScope.connected:
        if (myApps) provider.addOrRemoveFilter('My Apps', 'Apps');
        if (!installed) provider.addOrRemoveFilter('Installed Apps', 'Apps');
        MixpanelManager().appsTypeFilter('Installed Apps', true);
        break;
      case _AppsScope.mine:
        if (installed) provider.addOrRemoveFilter('Installed Apps', 'Apps');
        if (!myApps) provider.addOrRemoveFilter('My Apps', 'Apps');
        MixpanelManager().appsTypeFilter('My Apps', true);
        break;
    }
    provider.applyFilters();
  }

  // ----- Build helpers ------------------------------------------------------

  /// Pull capability pills from grouped apps so the row stays in sync with what
  /// the backend returns. We hide `memories` and `chat` (accessed elsewhere).
  List<CapabilityPill> _buildCapabilityPills(List<Map<String, dynamic>> groups) {
    final out = <CapabilityPill>[];
    for (final g in groups) {
      final cap = g['capability'] as Map<String, dynamic>?;
      final cat = g['category'] as Map<String, dynamic>?;
      final src = cap ?? cat;
      if (src == null) continue;
      final id = (src['id'] as String? ?? '').trim();
      if (id == 'memories' || id == 'chat') continue;
      final title = (src['title'] as String? ?? '').trim();
      if (id.isEmpty || title.isEmpty) continue;

      // Localize via AppCapability/Category helper for consistency with section headers.
      final label = cap != null
          ? AppCapability(title: title, id: id).getLocalizedTitle(context)
          : Category(title: title, id: id).getLocalizedTitle(context);
      out.add(CapabilityPill(id: id, label: label));
    }
    return out;
  }

  Widget _buildSearchAndFilters(_ToolbarState state) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
      child: Column(
        children: [
          // Search + filter row
          Row(
            children: [
              Expanded(child: _buildSearchField(state)),
              const SizedBox(width: 8),
              _buildFilterButton(state),
            ],
          ),
          const SizedBox(height: 10),
          // Segmented scope: All / Connected / Mine
          SegmentedFilter<_AppsScope>(
            value: state.scope,
            onChanged: _setScope,
            items: [
              SegmentedFilterItem(label: context.l10n.all, value: _AppsScope.all),
              SegmentedFilterItem(label: context.l10n.installed, value: _AppsScope.connected),
              SegmentedFilterItem(label: context.l10n.myApps, value: _AppsScope.mine),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSearchField(_ToolbarState state) {
    return SizedBox(
      height: 44,
      child: SearchBar(
        hintText: context.l10n.searchAppsPlaceholder,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8.0),
          child: Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white70, size: 14),
        ),
        backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
        elevation: WidgetStateProperty.all(0),
        padding: WidgetStateProperty.all(const EdgeInsets.symmetric(horizontal: 12, vertical: 4)),
        focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
        controller: searchController,
        trailing: state.searchActive
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
        hintStyle: WidgetStateProperty.all(TextStyle(color: AppStyles.textTertiary, fontSize: 14)),
        textStyle: WidgetStateProperty.all(const TextStyle(color: AppStyles.textPrimary, fontSize: 14)),
        shape: WidgetStateProperty.all(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppStyles.radiusLarge)),
        ),
        onChanged: (value) {
          debouncer.run(() {
            context.read<AppProvider>().searchApps(value);
          });
        },
      ),
    );
  }

  Widget _buildFilterButton(_ToolbarState state) {
    return SizedBox(
      width: 44,
      height: 44,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
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
              icon: const Icon(FontAwesomeIcons.filter, size: 14, color: Colors.white),
              padding: EdgeInsets.zero,
            ),
          ),
          if (state.visibleFilterCount > 0)
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
    );
  }

  Widget _buildFilteredAppsSlivers() {
    return Selector<AppProvider, List<App>>(
      selector: (context, provider) => provider.filteredApps,
      builder: (context, filteredApps, _) {
        if (filteredApps.isEmpty) return _buildEmptySliver();
        return SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 100),
          sliver: SliverList.separated(
            itemCount: filteredApps.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) => AppRowCard(app: filteredApps[index]),
          ),
        );
      },
    );
  }

  Widget _buildEmptySliver() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.25),
        child: Column(
          children: [
            Icon(Icons.search_off, size: 56, color: Colors.grey.shade600),
            const SizedBox(height: 12),
            Text(
              context.l10n.noAppsFound,
              style: const TextStyle(fontSize: 17, color: Colors.white70),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 6),
            Text(
              context.l10n.tryAdjustingSearch,
              style: TextStyle(fontSize: 13, color: Colors.grey.shade400),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  /// Renders all backend-grouped sections as vertical card-row sections.
  Widget _buildCategorizedAppsSlivers() {
    return Selector<AppProvider, List<Map<String, dynamic>>>(
      selector: (_, p) => p.groupedApps,
      builder: (context, groups, _) {
        final filteredGroups = groups.where((g) {
          final cap = g['capability'] as Map<String, dynamic>?;
          final id = cap?['id'] as String? ?? '';
          return id != 'memories' && id != 'chat';
        }).toList();

        // If a capability pill is selected, flatten only that group's apps.
        if (_selectedCapabilityId != null) {
          final selected = filteredGroups.firstWhere(
            (g) {
              final cap = g['capability'] as Map<String, dynamic>?;
              final cat = g['category'] as Map<String, dynamic>?;
              final id = (cap?['id'] ?? cat?['id']) as String? ?? '';
              return id == _selectedCapabilityId;
            },
            orElse: () => <String, dynamic>{},
          );
          final apps = selected['data'] as List<App>? ?? <App>[];
          if (apps.isEmpty) return _buildEmptySliver();
          return SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 100),
            sliver: SliverList.separated(
              itemCount: apps.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, i) => AppRowCard(app: apps[i]),
            ),
          );
        }

        return SliverPadding(
          padding: const EdgeInsets.only(bottom: 100),
          sliver: SliverList.builder(
            itemCount: filteredGroups.length,
            itemBuilder: (context, index) {
              final group = filteredGroups[index];
              final cap = group['capability'] as Map<String, dynamic>?;
              final cat = group['category'] as Map<String, dynamic>?;
              final src = cap ?? cat;
              final title = (src?['title'] as String? ?? '').trim();
              final id = (src?['id'] as String? ?? '').trim();
              final apps = group['data'] as List<App>? ?? <App>[];

              final localizedTitle = cap != null
                  ? AppCapability(
                      title: title.isEmpty ? 'Apps' : title,
                      id: id.isEmpty ? title.toLowerCase().replaceAll(' ', '_') : id,
                    ).getLocalizedTitle(context)
                  : context
                      .read<AddAppProvider>()
                      .categories
                      .firstWhere(
                        (c) => c.id == id || c.title == title,
                        orElse: () => Category(
                          title: title.isEmpty ? 'Apps' : title,
                          id: id.isEmpty ? title.toLowerCase().replaceAll(' ', '-') : id,
                        ),
                      )
                      .getLocalizedTitle(context);

              return AppSection(
                title: localizedTitle,
                apps: apps,
                onViewAll: apps.length > 4
                    ? () {
                        if (cap != null) {
                          final capability = AppCapability(
                            title: title.isEmpty ? 'Apps' : title,
                            id: id.isEmpty ? title.toLowerCase().replaceAll(' ', '_') : id,
                          );
                          routeToPage(context, CapabilityAppsPage(capability: capability, apps: apps));
                        } else {
                          final category = context.read<AddAppProvider>().categories.firstWhere(
                                (c) => c.id == id || c.title == title,
                                orElse: () => Category(
                                  title: title.isEmpty ? 'Apps' : title,
                                  id: id.isEmpty ? title.toLowerCase().replaceAll(' ', '-') : id,
                                ),
                              );
                          routeToPage(context, CategoryAppsPage(category: category, apps: apps));
                        }
                      }
                    : null,
              );
            },
          ),
        );
      },
    );
  }

  // ----- Shimmer skeletons --------------------------------------------------

  Widget _buildShimmerToolbar() {
    return ShimmerWithTimeout(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
        child: Column(
          children: [
            Row(
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
            const SizedBox(height: 10),
            Container(
              height: 36,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerSection() {
    return ShimmerWithTimeout(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 12),
            child: Row(
              children: [
                Container(
                  width: 140,
                  height: 18,
                  decoration: BoxDecoration(
                    color: AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const Spacer(),
                Container(
                  width: 60,
                  height: 14,
                  decoration: BoxDecoration(
                    color: AppStyles.backgroundSecondary,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ],
            ),
          ),
          for (int i = 0; i < 3; i++) ...[
            Container(
              height: 84,
              margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildShimmerAppsView() {
    return Column(
      children: [
        const SizedBox(height: 4),
        _buildShimmerSection(),
        _buildShimmerSection(),
        _buildShimmerSection(),
        const SizedBox(height: 100),
      ],
    );
  }

  Widget _buildSearchLoadingSliver() {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 100),
      sliver: SliverList.builder(
        itemCount: 5,
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: ShimmerWithTimeout(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              height: 84,
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ----- Main build ---------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return NotificationListener<SelectAppNotification>(
      onNotification: _handleSelectAppNotification,
      child: Selector<AppProvider, _ToolbarState>(
        selector: (context, p) {
          final visible = p.filters.entries.where((e) {
            if (e.key == 'Apps') return e.value != 'My Apps' && e.value != 'Installed Apps';
            return true;
          }).toList();
          return _ToolbarState(
            isLoading: p.isLoading,
            isSearching: p.isSearching,
            searchActive: p.isSearchActive(),
            filterActive: p.isFilterActive(),
            visibleFilterCount: visible.length,
            scope: _currentScope(p),
          );
        },
        builder: (context, state, _) {
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
                  child: state.isLoading ? _buildShimmerToolbar() : _buildSearchAndFilters(state),
                ),
                if (!state.isLoading && !state.searchActive && !state.filterActive)
                  SliverToBoxAdapter(child: _buildCapabilityPillsSection()),
                if (state.isLoading)
                  SliverToBoxAdapter(child: _buildShimmerAppsView())
                else if (state.isSearching)
                  _buildSearchLoadingSliver()
                else if (state.filterActive || state.searchActive)
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

  Widget _buildCapabilityPillsSection() {
    return Selector<AppProvider, List<Map<String, dynamic>>>(
      selector: (_, p) => p.groupedApps,
      builder: (context, groups, _) {
        final pills = _buildCapabilityPills(groups);
        if (pills.isEmpty) return const SizedBox(height: 4);
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: CapabilityPillsRow(
            pills: pills,
            selectedId: _selectedCapabilityId,
            onSelected: (id) => setState(() => _selectedCapabilityId = id),
          ),
        );
      },
    );
  }

  @override
  bool get wantKeepAlive => true;
}

class _ToolbarState {
  final bool isLoading;
  final bool isSearching;
  final bool searchActive;
  final bool filterActive;
  final int visibleFilterCount;
  final _AppsScope scope;

  _ToolbarState({
    required this.isLoading,
    required this.isSearching,
    required this.searchActive,
    required this.filterActive,
    required this.visibleFilterCount,
    required this.scope,
  });

  @override
  bool operator ==(Object other) =>
      other is _ToolbarState &&
      isLoading == other.isLoading &&
      isSearching == other.isSearching &&
      searchActive == other.searchActive &&
      filterActive == other.filterActive &&
      visibleFilterCount == other.visibleFilterCount &&
      scope == other.scope;

  @override
  int get hashCode => Object.hash(isLoading, isSearching, searchActive, filterActive, visibleFilterCount, scope);
}
