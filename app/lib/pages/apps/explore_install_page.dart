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
import 'package:omi/pages/apps/widgets/redesign/text_tabs.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';

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

class SelectAppNotification extends Notification {
  final App app;
  SelectAppNotification(this.app);
}

enum _Tab { discover, installed }

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

  static const Color _pageBg = Color(0xFF0F0F0F);
  static const Color _surface = Color(0xFF1A1A1F);

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

  // ----- Tab state ----------------------------------------------------------

  _Tab _currentTab(AppProvider provider) {
    if (provider.isFilterSelected('Installed Apps', 'Apps')) return _Tab.installed;
    return _Tab.discover;
  }

  void _setTab(_Tab tab) {
    final provider = context.read<AppProvider>();
    final installed = provider.isFilterSelected('Installed Apps', 'Apps');

    switch (tab) {
      case _Tab.discover:
        if (installed) provider.addOrRemoveFilter('Installed Apps', 'Apps');
        break;
      case _Tab.installed:
        if (!installed) {
          provider.addOrRemoveFilter('Installed Apps', 'Apps');
          MixpanelManager().appsTypeFilter('Installed Apps', true);
        }
        break;
    }
    provider.applyFilters();
  }

  // ----- Toolbar ------------------------------------------------------------

  Widget _buildToolbar(_ToolbarState state) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: _buildSearchField(state)),
              const SizedBox(width: 10),
              _buildFilterButton(state),
            ],
          ),
          const SizedBox(height: 20),
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: TextTabs<_Tab>(
              value: state.tab,
              onChanged: _setTab,
              items: [
                TextTabItem(label: context.l10n.all, value: _Tab.discover),
                TextTabItem(label: context.l10n.installed, value: _Tab.installed),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchField(_ToolbarState state) {
    return Container(
      height: 48,
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          const SizedBox(width: 16),
          const Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white54, size: 14),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: searchController,
              focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
              style: const TextStyle(color: Colors.white, fontSize: 15, letterSpacing: -0.2),
              cursorColor: const Color(0xFF8B5CF6),
              decoration: InputDecoration(
                isCollapsed: true,
                contentPadding: const EdgeInsets.symmetric(vertical: 14),
                border: InputBorder.none,
                hintText: context.l10n.searchAppsPlaceholder,
                hintStyle: TextStyle(color: Colors.grey.shade600, fontSize: 15, letterSpacing: -0.2),
              ),
              onChanged: (value) {
                debouncer.run(() {
                  context.read<AppProvider>().searchApps(value);
                });
              },
            ),
          ),
          if (state.searchActive)
            IconButton(
              icon: const Icon(Icons.close_rounded, color: Colors.white54, size: 18),
              padding: const EdgeInsets.symmetric(horizontal: 12),
              constraints: const BoxConstraints(),
              onPressed: () {
                searchController.clear();
                context.read<AppProvider>().searchApps('');
              },
            ),
        ],
      ),
    );
  }

  Widget _buildFilterButton(_ToolbarState state) {
    final hasFilters = state.visibleFilterCount > 0;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: _surface,
            borderRadius: BorderRadius.circular(14),
          ),
          child: IconButton(
            onPressed: () {
              HapticFeedback.mediumImpact();
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (_) => const FilterBottomSheet(),
              );
            },
            icon: Icon(
              hasFilters ? FontAwesomeIcons.solidStar : Icons.tune_rounded,
              size: hasFilters ? 14 : 18,
              color: hasFilters ? const Color(0xFF8B5CF6) : Colors.white70,
            ),
            padding: EdgeInsets.zero,
          ),
        ),
        if (hasFilters)
          Positioned(
            top: -4,
            right: -4,
            child: Container(
              padding: const EdgeInsets.all(4),
              decoration: const BoxDecoration(color: Color(0xFF8B5CF6), shape: BoxShape.circle),
              constraints: const BoxConstraints(minWidth: 18, minHeight: 18),
              child: Center(
                child: Text(
                  state.visibleFilterCount.toString(),
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700, height: 1.0),
                ),
              ),
            ),
          ),
      ],
    );
  }

  // ----- Body ---------------------------------------------------------------

  Widget _buildFilteredAppsSlivers() {
    return Selector<AppProvider, List<App>>(
      selector: (context, provider) => provider.filteredApps,
      builder: (context, filteredApps, _) {
        if (filteredApps.isEmpty) return _buildEmptySliver();
        return SliverPadding(
          padding: const EdgeInsets.fromLTRB(24, 12, 24, 100),
          sliver: SliverList.builder(
            itemCount: filteredApps.length,
            itemBuilder: (context, index) {
              return Column(
                children: [
                  AppRowCard(app: filteredApps[index]),
                  if (index != filteredApps.length - 1)
                    Padding(
                      padding: const EdgeInsets.only(left: 70),
                      child: Container(height: 0.5, color: Colors.white.withValues(alpha: 0.06)),
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  Widget _buildEmptySliver() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.18),
        child: Column(
          children: [
            Icon(Icons.search_off_rounded, size: 48, color: Colors.grey.shade700),
            const SizedBox(height: 14),
            Text(
              context.l10n.noAppsFound,
              style: const TextStyle(fontSize: 17, color: Colors.white, fontWeight: FontWeight.w600),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 6),
            Text(
              context.l10n.tryAdjustingSearch,
              style: TextStyle(fontSize: 14, color: Colors.grey.shade500),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategorizedAppsSlivers() {
    return Selector<AppProvider, List<Map<String, dynamic>>>(
      selector: (_, p) => p.groupedApps,
      builder: (context, groups, _) {
        final filteredGroups = groups.where((g) {
          final cap = g['capability'] as Map<String, dynamic>?;
          final id = cap?['id'] as String? ?? '';
          return id != 'memories' && id != 'chat';
        }).toList();

        if (filteredGroups.isEmpty) return _buildEmptySliver();

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
                onViewAll: apps.length > 5
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

  // ----- Shimmers -----------------------------------------------------------

  Widget _buildShimmerToolbar() {
    return ShimmerWithTimeout(
      baseColor: _surface,
      highlightColor: const Color(0xFF2A2A30),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 16, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Container(
                    height: 48,
                    decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(14)),
                  ),
                ),
                const SizedBox(width: 10),
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(14)),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Container(
              width: 180,
              height: 18,
              decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildShimmerSection() {
    return ShimmerWithTimeout(
      baseColor: _surface,
      highlightColor: const Color(0xFF2A2A30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 36, 24, 16),
            child: Container(
              width: 160,
              height: 22,
              decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
            ),
          ),
          for (int i = 0; i < 4; i++)
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 14, 24, 14),
              child: Row(
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(14)),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 120,
                          height: 16,
                          decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
                        ),
                        const SizedBox(height: 8),
                        Container(
                          width: double.infinity,
                          height: 13,
                          decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildShimmerAppsView() {
    return Column(
      children: [
        _buildShimmerSection(),
        _buildShimmerSection(),
        const SizedBox(height: 100),
      ],
    );
  }

  Widget _buildSearchLoadingSliver() {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(24, 12, 24, 100),
      sliver: SliverList.builder(
        itemCount: 5,
        itemBuilder: (_, __) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 14),
          child: ShimmerWithTimeout(
            baseColor: _surface,
            highlightColor: const Color(0xFF2A2A30),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(14)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 120,
                        height: 16,
                        decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
                      ),
                      const SizedBox(height: 8),
                      Container(
                        width: double.infinity,
                        height: 13,
                        decoration: BoxDecoration(color: _surface, borderRadius: BorderRadius.circular(4)),
                      ),
                    ],
                  ),
                ),
              ],
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
    return Container(
      color: _pageBg,
      child: NotificationListener<SelectAppNotification>(
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
              tab: _currentTab(p),
            );
          },
          builder: (context, state, _) {
            return RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.mediumImpact();
                await context.read<AppProvider>().forceRefreshApps();
              },
              color: const Color(0xFF8B5CF6),
              backgroundColor: _surface,
              child: CustomScrollView(
                controller: widget.scrollController,
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  SliverToBoxAdapter(
                    child: state.isLoading ? _buildShimmerToolbar() : _buildToolbar(state),
                  ),
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
      ),
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
  final _Tab tab;

  _ToolbarState({
    required this.isLoading,
    required this.isSearching,
    required this.searchActive,
    required this.filterActive,
    required this.visibleFilterCount,
    required this.tab,
  });

  @override
  bool operator ==(Object other) =>
      other is _ToolbarState &&
      isLoading == other.isLoading &&
      isSearching == other.isSearching &&
      searchActive == other.searchActive &&
      filterActive == other.filterActive &&
      visibleFilterCount == other.visibleFilterCount &&
      tab == other.tab;

  @override
  int get hashCode => Object.hash(isLoading, isSearching, searchActive, filterActive, visibleFilterCount, tab);
}
