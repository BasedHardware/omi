import 'dart:ui';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';
import 'widgets/desktop_app_grid.dart';
import 'widgets/desktop_filter_chips.dart';
import 'widgets/desktop_app_detail.dart';
import 'package:omi/ui/atoms/omi_search_input.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';

class DesktopAppsPage extends StatefulWidget {
  final VoidCallback? onNavigateToCreateApp;

  const DesktopAppsPage({
    super.key,
    this.onNavigateToCreateApp,
  });

  @override
  State<DesktopAppsPage> createState() => _DesktopAppsPageState();
}

class _DesktopAppsPageState extends State<DesktopAppsPage> with AutomaticKeepAliveClientMixin {
  late TextEditingController _searchController;
  late FocusNode _searchFocusNode;
  final Debouncer _debouncer = Debouncer(delay: const Duration(milliseconds: 500));
  late ScrollController _scrollController;

  bool _isInitialized = false;
  bool _isLoadingData = false;

  final ValueNotifier<App?> _selectedAppNotifier = ValueNotifier<App?>(null);

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    _searchFocusNode = FocusNode();
    _scrollController = ScrollController();

    _initializeDataSequentially();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppProvider>().addListener(_handleAppProviderChange);
      MixpanelManager().pageOpened('Apps');
    });
  }

  void _handleAppProviderChange() {
    // Check if we need to refresh the category-based content
    if (mounted && _isInitialized) {
      // Small delay to ensure all state updates are complete
      Future.delayed(const Duration(milliseconds: 100), () {
        if (mounted) {
          setState(() {});
        }
      });
    }
  }

  /// Sequential initialization to prevent database locks
  Future<void> _initializeDataSequentially() async {
    if (_isLoadingData) return;

    setState(() {
      _isLoadingData = true;
    });

    try {
      // Load from cache first for immediate UI
      final appProvider = context.read<AppProvider>();
      if (appProvider.apps.isEmpty) {
        appProvider.setAppsFromCache();
      }

      // Sequential loading to avoid database conflicts
      await Future.delayed(const Duration(milliseconds: 100));

      if (mounted) {
        // Load categories first (smaller dataset)
        await context.read<AddAppProvider>().getCategories();

        // Small delay between operations
        await Future.delayed(const Duration(milliseconds: 50));

        if (mounted) {
          // Initialize capabilities
          await context.read<AddAppProvider>().getAppCapabilities();

          // Load popular apps
          await Future.delayed(const Duration(milliseconds: 50));
          if (mounted) {
            await context.read<AppProvider>().getPopularApps();
          }

          setState(() {
            _isInitialized = true;
            _isLoadingData = false;
          });
        }
      }
    } catch (e) {
      debugPrint('Error during initialization: $e');
      setState(() {
        _isLoadingData = false;
      });
    }
  }

  @override
  void dispose() {
    try {
      context.read<AppProvider>().removeListener(_handleAppProviderChange);
    } catch (e) {
      debugPrint('Could not remove AppProvider listener: $e');
    }

    _searchController.dispose();
    _searchFocusNode.dispose();
    _scrollController.dispose();
    _selectedAppNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final responsive = ResponsiveHelper(context);

    return Consumer<AppProvider>(
      builder: (context, appProvider, _) {
        if (_isLoadingData && appProvider.apps.isEmpty) {
          return _buildLoadingState(responsive);
        }

        return Stack(
          children: [
            Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundPrimary.withValues(alpha: 0.8),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  _buildHeader(responsive, appProvider),
                  if (appProvider.isFilterActive()) _buildActiveFilters(responsive, appProvider),
                  Expanded(
                    child: _buildContent(responsive, appProvider),
                  ),
                ],
              ),
            ),

            // Panel overlay
            ValueListenableBuilder<App?>(
              valueListenable: _selectedAppNotifier,
              builder: (context, selectedApp, child) {
                if (selectedApp == null) return const SizedBox.shrink();

                return Stack(
                  children: [
                    // Backdrop blur overlay
                    Positioned.fill(
                      child: GestureDetector(
                        onTap: () {
                          _selectedAppNotifier.value = null;
                        },
                        child: BackdropFilter(
                          filter: ImageFilter.blur(sigmaX: 8.0, sigmaY: 8.0),
                          child: Container(
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundPrimary.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(16),
                            ),
                          ),
                        ),
                      ),
                    ),
                    // App detail panel
                    Positioned(
                      top: 0,
                      right: 0,
                      bottom: 0,
                      child: DesktopAppDetail(
                        app: selectedApp,
                        onClose: () {
                          _selectedAppNotifier.value = null;
                        },
                      ),
                    ),
                  ],
                );
              },
            ),
          ],
        );
      },
    );
  }

  Widget _buildLoadingState(ResponsiveHelper responsive) {
    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundPrimary.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
            ),
            SizedBox(height: responsive.spacing(baseSpacing: 16)),
            Text(
              'Loading apps...',
              style: responsive.bodyLarge.copyWith(
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(ResponsiveHelper responsive, AppProvider appProvider) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Title and search row
          Row(
            children: [
              // Title
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Apps',
                      style: responsive.headlineLarge.copyWith(
                        color: ResponsiveHelper.textPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: responsive.spacing(baseSpacing: 4)),
                    Consumer<ConnectivityProvider>(
                      builder: (context, connectivityProvider, _) {
                        if (!connectivityProvider.isConnected) {
                          return Text(
                            'No internet connection',
                            style: responsive.bodyMedium.copyWith(
                              color: ResponsiveHelper.errorColor,
                            ),
                          );
                        }

                        return Text(
                          'Browse, install, and create apps',
                          style: responsive.bodyMedium.copyWith(
                            color: ResponsiveHelper.textTertiary,
                          ),
                        );
                      },
                    ),
                  ],
                ),
              ),

              // Search bar - prominent like App Store
              SizedBox(
                width: responsive.responsiveWidth(baseWidth: 400, maxWidth: 500),
                child: OmiSearchInput(
                  controller: _searchController,
                  focusNode: _searchFocusNode,
                  onChanged: (query) => _debouncer.run(() {
                    appProvider.searchApps(query);
                    if (query.isNotEmpty) {
                      MixpanelManager().memorySearched(query, appProvider.filteredApps.length);
                    }
                  }),
                  onClear: () {
                    _searchController.clear();
                    appProvider.searchApps('');
                    MixpanelManager().memorySearchCleared(appProvider.apps.length);
                    _searchFocusNode.unfocus();
                  },
                  hint: 'Search apps...',
                ),
              ),

              const SizedBox(width: 12),

              // Create App button
              OmiButton(
                label: 'Create App',
                icon: Icons.add_rounded,
                onPressed: () {
                  MixpanelManager().pageOpened('Submit App');
                  _navigateToCreateApp(context);
                },
                type: OmiButtonType.primary,
              ),
            ],
          ),

          SizedBox(height: responsive.spacing(baseSpacing: 24)),

          // Filter chips row - only show when initialized
          if (_isInitialized)
            DesktopFilterChips(
              onFilterChanged: () {
                // Debounce filter operations for better performance
                _debouncer.run(() {
                  appProvider.filterApps();
                });
              },
            ),
        ],
      ),
    );
  }

  Widget _buildActiveFilters(ResponsiveHelper responsive, AppProvider appProvider) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: responsive.spacing(baseSpacing: 32),
        vertical: responsive.spacing(baseSpacing: 8),
      ),
      child: Row(
        children: [
          Text(
            'Active filters:',
            style: responsive.bodySmall.copyWith(
              color: ResponsiveHelper.textTertiary,
            ),
          ),
          SizedBox(width: responsive.spacing(baseSpacing: 12)),
          Expanded(
            child: Wrap(
              spacing: responsive.spacing(baseSpacing: 8),
              runSpacing: responsive.spacing(baseSpacing: 4),
              children: appProvider.filters.entries.map((entry) {
                return _buildActiveFilterChip(responsive, appProvider, entry.key, entry.value);
              }).toList(),
            ),
          ),
          // Clear all button
          TextButton.icon(
            onPressed: () {
              MixpanelManager().appsClearFilters();
              appProvider.clearFilters();
            },
            icon: const Icon(Icons.clear_all, size: 16),
            label: Text(
              'Clear all',
              style: responsive.bodySmall.copyWith(
                fontWeight: FontWeight.w500,
              ),
            ),
            style: TextButton.styleFrom(
              foregroundColor: ResponsiveHelper.purplePrimary,
              padding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 12),
                vertical: responsive.spacing(baseSpacing: 4),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveFilterChip(ResponsiveHelper responsive, AppProvider appProvider, String key, dynamic value) {
    String displayText = '';
    if (value is String) {
      displayText = value;
    } else if (value is Category) {
      // Handle Category objects
      displayText = value.title;
    } else if (value is AppCapability) {
      // Handle AppCapability objects
      displayText = value.title;
    } else {
      displayText = value.toString();
    }

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: responsive.spacing(baseSpacing: 12),
        vertical: responsive.spacing(baseSpacing: 6),
      ),
      decoration: BoxDecoration(
        color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            displayText,
            style: responsive.bodySmall.copyWith(
              color: ResponsiveHelper.purplePrimary,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(width: responsive.spacing(baseSpacing: 6)),
          GestureDetector(
            onTap: () {
              // Track filter removal based on filter type
              if (value is Category) {
                MixpanelManager().appsCategoryFilter(value.title, false);
              } else if (value is AppCapability) {
                MixpanelManager().appsCapabilityFilter(value.title, false);
              } else if (value is String) {
                if (value == 'Installed Apps' || value == 'My Apps') {
                  MixpanelManager().appsTypeFilter(value, false);
                } else if (value.startsWith('1+') ||
                    value.startsWith('2+') ||
                    value.startsWith('3+') ||
                    value.startsWith('4+')) {
                  MixpanelManager().appsRatingFilter(value, false);
                } else if (value == 'A-Z' || value == 'Z-A' || value == 'Highest Rating' || value == 'Lowest Rating') {
                  MixpanelManager().appsSortFilter(value, false);
                }
              }
              appProvider.removeFilter(key);
            },
            child: const Icon(
              Icons.close,
              size: 14,
              color: ResponsiveHelper.purplePrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(ResponsiveHelper responsive, AppProvider appProvider) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        responsive.spacing(baseSpacing: 32),
        0,
        responsive.spacing(baseSpacing: 32),
        responsive.spacing(baseSpacing: 32),
      ),
      child: CustomScrollView(
        controller: _scrollController,
        slivers: [
          // Show category-based layout when not filtering/searching
          if (!appProvider.isFilterActive() && !appProvider.isSearchActive())
            ..._buildCategoryBasedContent(responsive, appProvider)
          else
            // Show filtered/searched apps in grid when filtering/searching
            _buildAppsGrid(responsive, appProvider),
        ],
      ),
    );
  }

  Widget _buildPopularAppsSection(ResponsiveHelper responsive, AppProvider appProvider) {
    // Limit popular apps to prevent UI lag
    final limitedPopularApps = appProvider.popularApps.take(8).toList();

    return SliverToBoxAdapter(
      child: Container(
        margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 32)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.trending_up_rounded,
                  color: ResponsiveHelper.purplePrimary,
                  size: 20,
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                Text(
                  'Popular',
                  style: responsive.titleMedium.copyWith(
                    color: ResponsiveHelper.textPrimary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),

            SizedBox(height: responsive.spacing(baseSpacing: 16)),

            // Horizontal scrolling popular apps
            SizedBox(
              height: 120, // Match fixed card height
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: limitedPopularApps.length,
                separatorBuilder: (context, index) => const SizedBox(width: 16),
                itemBuilder: (context, index) {
                  final app = limitedPopularApps[index];
                  return _buildPopularAppCard(responsive, app);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPopularAppCard(ResponsiveHelper responsive, App app) {
    return SizedBox(
      width: 320, // Fixed width to match category cards
      height: 120, // Increased height for better content spacing
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _handleAppTap(app),
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                // App icon
                CachedNetworkImage(
                  imageUrl: app.getImageUrl(),
                  imageBuilder: (context, imageProvider) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      image: DecorationImage(
                        image: imageProvider,
                        fit: BoxFit.cover,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                  ),
                  placeholder: (context, url) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                    child: const Icon(
                      Icons.apps,
                      color: ResponsiveHelper.textQuaternary,
                      size: 24,
                    ),
                  ),
                  errorWidget: (context, url, error) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                    child: const Icon(
                      Icons.apps,
                      color: ResponsiveHelper.textQuaternary,
                      size: 24,
                    ),
                  ),
                ),

                const SizedBox(width: 16),

                // App info - takes remaining space
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // App name
                      Text(
                        app.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: ResponsiveHelper.textPrimary,
                          height: 1.2,
                        ),
                      ),

                      const SizedBox(height: 6),

                      // App description - reduced opacity and better spacing
                      Text(
                        app.description.decodeString,
                        maxLines: 2, // Back to 2 lines with increased card height
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          color: ResponsiveHelper.textTertiary.withValues(alpha: 0.7), // Reduced opacity
                          height: 1.3,
                        ),
                      ),

                      const SizedBox(height: 8),

                      // Rating and install status
                      Row(
                        children: [
                          if (app.ratingAvg != null) ...[
                            const Icon(
                              Icons.star_rounded,
                              color: ResponsiveHelper.purplePrimary,
                              size: 14,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              app.getRatingAvg()!,
                              style: const TextStyle(
                                color: ResponsiveHelper.textSecondary,
                                fontSize: 11,
                                height: 1.2,
                              ),
                            ),
                            const Spacer(),
                          ] else
                            const Spacer(),
                          if (app.enabled)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'Installed',
                                style: TextStyle(
                                  color: ResponsiveHelper.purplePrimary,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w500,
                                  height: 1.2,
                                ),
                              ),
                            ),
                        ],
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

  List<Widget> _buildCategoryBasedContent(ResponsiveHelper responsive, AppProvider appProvider) {
    List<Widget> slivers = [];

    // Popular apps section first
    if (appProvider.popularApps.isNotEmpty) {
      slivers.add(_buildPopularAppsSection(responsive, appProvider));
    }

    // Get available categories from AddAppProvider
    final categories = context.read<AddAppProvider>().categories;

    if (categories.isEmpty) {
      // Show loading state instead of all apps to prevent initial flash
      return [
        SliverFillRemaining(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                ),
                SizedBox(height: responsive.spacing(baseSpacing: 16)),
                Text(
                  'Loading categories...',
                  style: responsive.bodyLarge.copyWith(
                    color: ResponsiveHelper.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ];
    }

    // Group apps by category
    final Map<String, List<App>> appsByCategory = {};
    for (final app in appProvider.apps) {
      final categoryId = app.category;
      if (categoryId.isNotEmpty) {
        appsByCategory[categoryId] ??= [];
        appsByCategory[categoryId]!.add(app);
      }
    }

    // Build category sections
    for (final category in categories) {
      final categoryApps = appsByCategory[category.id] ?? [];
      if (categoryApps.isNotEmpty) {
        slivers.add(_buildCategorySection(responsive, appProvider, category, categoryApps));
      }
    }

    // Add uncategorized apps if any
    final uncategorizedApps = appProvider.apps.where((app) => app.category.isEmpty).toList();
    if (uncategorizedApps.isNotEmpty) {
      slivers.add(_buildUncategorizedSection(responsive, appProvider, uncategorizedApps));
    }

    return slivers;
  }

  Widget _buildCategorySection(
      ResponsiveHelper responsive, AppProvider appProvider, dynamic category, List<App> categoryApps) {
    // Show up to 8 apps from this category
    final displayApps = categoryApps.take(8).toList();

    return SliverToBoxAdapter(
      child: Container(
        margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 32)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Category header with name and view all button
            Row(
              children: [
                const Icon(
                  Icons.category_rounded,
                  color: ResponsiveHelper.purplePrimary,
                  size: 20,
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                Text(
                  category.title,
                  style: responsive.titleMedium.copyWith(
                    color: ResponsiveHelper.textPrimary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: responsive.spacing(baseSpacing: 6),
                    vertical: responsive.spacing(baseSpacing: 2),
                  ),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    '${categoryApps.length}',
                    style: responsive.bodySmall.copyWith(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 10,
                    ),
                  ),
                ),
                const Spacer(),
                if (categoryApps.length > 8)
                  TextButton.icon(
                    onPressed: () {
                      // Apply category filter
                      MixpanelManager().appsCategoryFilter(category.title, true);
                      appProvider.addOrRemoveCategoryFilter(category);
                    },
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: Text(
                      'View All',
                      style: responsive.bodyMedium.copyWith(
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    iconAlignment: IconAlignment.end, // Icon after text
                    style: TextButton.styleFrom(
                      foregroundColor: ResponsiveHelper.purplePrimary,
                      padding: EdgeInsets.symmetric(
                        horizontal: responsive.spacing(baseSpacing: 12),
                        vertical: responsive.spacing(baseSpacing: 4),
                      ),
                    ),
                  ),
              ],
            ),

            SizedBox(height: responsive.spacing(baseSpacing: 16)),

            // Horizontal scrolling apps
            SizedBox(
              height: 120, // Fixed height to match card dimensions
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: displayApps.length,
                separatorBuilder: (context, index) => const SizedBox(width: 16),
                itemBuilder: (context, index) {
                  final app = displayApps[index];
                  return _buildCategoryAppCard(responsive, app);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUncategorizedSection(ResponsiveHelper responsive, AppProvider appProvider, List<App> uncategorizedApps) {
    final displayApps = uncategorizedApps.take(8).toList();

    return SliverToBoxAdapter(
      child: Container(
        margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 32)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.apps_rounded,
                  color: ResponsiveHelper.textTertiary,
                  size: 20,
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                Text(
                  'Other Apps',
                  style: responsive.titleMedium.copyWith(
                    color: ResponsiveHelper.textPrimary,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                SizedBox(width: responsive.spacing(baseSpacing: 8)),
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: responsive.spacing(baseSpacing: 6),
                    vertical: responsive.spacing(baseSpacing: 2),
                  ),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    '${uncategorizedApps.length}',
                    style: responsive.bodySmall.copyWith(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 10,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 120, // Fixed height to match card dimensions
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: displayApps.length,
                separatorBuilder: (context, index) => const SizedBox(width: 16),
                itemBuilder: (context, index) {
                  final app = displayApps[index];
                  return _buildCategoryAppCard(responsive, app);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryAppCard(ResponsiveHelper responsive, App app) {
    return SizedBox(
      width: 320,
      height: 120,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _handleAppTap(app),
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                // App icon
                CachedNetworkImage(
                  imageUrl: app.getImageUrl(),
                  imageBuilder: (context, imageProvider) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      image: DecorationImage(
                        image: imageProvider,
                        fit: BoxFit.cover,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.1),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                  ),
                  placeholder: (context, url) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                    child: const Icon(
                      Icons.apps,
                      color: ResponsiveHelper.textQuaternary,
                      size: 24,
                    ),
                  ),
                  errorWidget: (context, url, error) => Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                    ),
                    child: const Icon(
                      Icons.apps,
                      color: ResponsiveHelper.textQuaternary,
                      size: 24,
                    ),
                  ),
                ),

                const SizedBox(width: 16),

                // App info - takes remaining space
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // App name
                      Text(
                        app.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: ResponsiveHelper.textPrimary,
                          height: 1.2,
                        ),
                      ),

                      const SizedBox(height: 6),

                      // App description - reduced opacity and better spacing
                      Text(
                        app.description.decodeString,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          color: ResponsiveHelper.textTertiary.withValues(alpha: 0.7),
                          height: 1.3,
                        ),
                      ),

                      const SizedBox(height: 8),

                      // Rating and install status
                      Row(
                        children: [
                          if (app.ratingAvg != null) ...[
                            const Icon(
                              Icons.star_rounded,
                              color: ResponsiveHelper.purplePrimary,
                              size: 14,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              app.getRatingAvg()!,
                              style: const TextStyle(
                                color: ResponsiveHelper.textSecondary,
                                fontSize: 11,
                                height: 1.2,
                              ),
                            ),
                            const Spacer(),
                          ] else
                            const Spacer(),
                          if (app.enabled)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: const Text(
                                'Installed',
                                style: TextStyle(
                                  color: ResponsiveHelper.purplePrimary,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w500,
                                  height: 1.2,
                                ),
                              ),
                            ),
                        ],
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

  Widget _buildAppsGrid(ResponsiveHelper responsive, AppProvider appProvider) {
    final apps =
        appProvider.isFilterActive() || appProvider.isSearchActive() ? appProvider.filteredApps : appProvider.apps;

    if (apps.isEmpty) {
      return SliverFillRemaining(
        child: _buildEmptyState(responsive, appProvider),
      );
    }

    return SliverToBoxAdapter(
      child: DesktopAppGrid(
        apps: apps,
        onAppTap: (app) => _handleAppTap(app),
      ),
    );
  }

  Widget _buildEmptyState(ResponsiveHelper responsive, AppProvider appProvider) {
    final title = appProvider.isSearchActive()
        ? 'No apps found'
        : context.read<ConnectivityProvider>().isConnected
            ? 'No apps available'
            : 'Unable to load apps';

    final message = appProvider.isSearchActive()
        ? 'Try adjusting your search terms or filters'
        : context.read<ConnectivityProvider>().isConnected
            ? 'Check back later for new apps'
            : 'Please check your internet connection and try again';

    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 400),
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 48)),
        child: OmiEmptyState(
          icon: Icons.apps_outlined,
          title: title,
          message: message,
          color: ResponsiveHelper.purplePrimary,
          iconSize: 48,
          iconPadding: 24,
        ),
      ),
    );
  }

  void _handleAppTap(App app) {
    MixpanelManager().pageOpened('App Detail');
    _selectedAppNotifier.value = app;
  }

  @override
  bool get wantKeepAlive => true;

  void _navigateToCreateApp(BuildContext context) {
    // Use callback to navigate within the same window structure
    if (widget.onNavigateToCreateApp != null) {
      widget.onNavigateToCreateApp!();
    }
  }
}
