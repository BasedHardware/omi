import 'dart:ui';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';
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
  bool _isReloading = false;
  late FocusNode _focusNode;

  final ValueNotifier<App?> _selectedAppNotifier = ValueNotifier<App?>(null);

  void _requestFocusIfPossible() {
    if (mounted && _focusNode.canRequestFocus) {
      _focusNode.requestFocus();
    }
  }

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    _searchFocusNode = FocusNode();
    _scrollController = ScrollController();
    _focusNode = FocusNode();

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

  void _handleReload() async {
    if (_isReloading) return;

    setState(() {
      _isReloading = true;
    });

    // Scroll to top
    if (_scrollController.hasClients) {
      await _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }

    final appProvider = Provider.of<AppProvider>(context, listen: false);
    await appProvider.getApps();

    if (mounted) {
      setState(() {
        _isReloading = false;
      });
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocusIfPossible());
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
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final responsive = ResponsiveHelper(context);

    return VisibilityDetector(
        key: const Key('desktop_apps_page'),
        onVisibilityChanged: (visibilityInfo) {
          if (visibilityInfo.visibleFraction > 0.1) {
            WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocusIfPossible());
          }
        },
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.keyR, meta: true): _handleReload,
          },
          child: Focus(
            focusNode: _focusNode,
            autofocus: true,
            child: GestureDetector(
              onTap: () {
                if (!_focusNode.hasFocus) {
                  _focusNode.requestFocus();
                }
              },
              child: Consumer<AppProvider>(
                builder: (context, appProvider, _) {
                  if (_isLoadingData && appProvider.apps.isEmpty) {
                    return _buildLoadingState(responsive);
                  }

                  final loadingWidget = _isReloading
                      ? Container(
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
                                  'Reloading apps...',
                                  style: responsive.bodyLarge.copyWith(
                                    color: ResponsiveHelper.textSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        )
                      : null;

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

                      // Loading overlay
                      if (loadingWidget != null) Positioned.fill(child: loadingWidget),
                    ],
                  );
                },
              ),
            ),
          ),
        ));
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
          // Title row
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

          SizedBox(height: responsive.spacing(baseSpacing: 20)),

          // Search and filter row - matching mobile style
          _buildSearchAndFiltersRow(responsive, appProvider),
        ],
      ),
    );
  }

  Widget _buildSearchAndFiltersRow(ResponsiveHelper responsive, AppProvider appProvider) {
    final isSearchActive = appProvider.isSearchActive();
    final isMyAppsSelected = appProvider.isFilterSelected('My Apps', 'Apps');
    final isInstalledSelected = appProvider.isFilterSelected('Installed Apps', 'Apps');

    return Row(
      children: [
        // Search bar
        Expanded(
          flex: isSearchActive ? 3 : 2,
          child: SizedBox(
            height: 44,
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
        ),

        const SizedBox(width: 12),

        // My Apps button
        _buildFilterButton(
          label: 'My Apps',
          icon: FontAwesomeIcons.solidUser,
          isSelected: isMyAppsSelected,
          onTap: () {
            HapticFeedback.mediumImpact();
            final wasSelected = appProvider.isFilterSelected('My Apps', 'Apps');
            appProvider.addOrRemoveFilter('My Apps', 'Apps');
            appProvider.applyFilters();
            MixpanelManager().appsTypeFilter('My Apps', !wasSelected);
          },
        ),

        const SizedBox(width: 8),

        // Installed Apps button
        _buildFilterButton(
          label: 'Installed Apps',
          icon: FontAwesomeIcons.download,
          isSelected: isInstalledSelected,
          onTap: () {
            HapticFeedback.mediumImpact();
            final wasSelected = appProvider.isFilterSelected('Installed Apps', 'Apps');
            appProvider.addOrRemoveFilter('Installed Apps', 'Apps');
            appProvider.applyFilters();
            MixpanelManager().appsTypeFilter('Installed Apps', !wasSelected);
          },
        ),
      ],
    );
  }

  Widget _buildFilterButton({
    required String label,
    required IconData icon,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            color: isSelected
                ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.3)
                : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected
                  ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.5)
                  : ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              FaIcon(
                icon,
                size: 14,
                color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
                ),
              ),
            ],
          ),
        ),
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
          // Show capability-based layout when not filtering/searching (like mobile)
          if (!appProvider.isFilterActive() && !appProvider.isSearchActive())
            ..._buildCapabilityBasedContent(responsive, appProvider)
          else
            // Show filtered/searched apps in grid when filtering/searching
            _buildAppsGrid(responsive, appProvider),
        ],
      ),
    );
  }

  List<Widget> _buildCapabilityBasedContent(ResponsiveHelper responsive, AppProvider appProvider) {
    List<Widget> slivers = [];

    // Use groupedApps from AppProvider (capability-based, like mobile)
    final groups = appProvider.groupedApps;

    if (groups.isEmpty) {
      // Show loading state
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
                  'Loading apps...',
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

    // Filter out sections that are accessed elsewhere (like mobile):
    // - "Summary" (memories) section - accessed via conversation detail page
    // - "Chat Assistants" (chat) section - accessed via chat page drawer
    final filteredGroups = groups.where((group) {
      final capabilityMap = group['capability'] as Map<String, dynamic>?;
      final groupId = capabilityMap?['id'] as String? ?? '';
      return groupId != 'memories' && groupId != 'chat';
    }).toList();

    // Build capability sections
    for (final group in filteredGroups) {
      final capabilityMap = group['capability'] as Map<String, dynamic>?;
      final categoryMap = group['category'] as Map<String, dynamic>?;

      final groupMap = capabilityMap ?? categoryMap;
      final groupTitle = (groupMap != null ? (groupMap['title'] as String? ?? '') : '').trim();
      final groupApps = group['data'] as List<App>? ?? <App>[];

      if (groupApps.isNotEmpty) {
        slivers.add(_buildCapabilitySection(responsive, groupTitle, groupApps));
      }
    }

    return slivers;
  }

  Widget _buildCapabilitySection(ResponsiveHelper responsive, String title, List<App> apps) {
    // Show up to 9 apps from this capability (like mobile)
    final displayApps = apps.take(9).toList();

    // Calculate grid height based on number of rows (3 items per column, scrolls horizontally)
    final numRows = displayApps.length.clamp(1, 3);
    final gridHeight = numRows * 80.0 + (numRows - 1) * 12.0;

    return SliverToBoxAdapter(
      child: Container(
        margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 28)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Section header - clean like mobile
            Row(
              children: [
                Text(
                  title.isEmpty ? 'Apps' : title,
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                const Spacer(),
                if (apps.length > 9)
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        // TODO: Navigate to full category view
                      },
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              'All',
                              style: TextStyle(
                                fontSize: 12,
                                color: ResponsiveHelper.textTertiary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            SizedBox(width: 2),
                            Icon(
                              Icons.chevron_right,
                              color: ResponsiveHelper.textTertiary,
                              size: 16,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),

            const SizedBox(height: 16),

            // Horizontal scrolling grid (3 rows like mobile)
            SizedBox(
              height: gridHeight,
              child: GridView.builder(
                scrollDirection: Axis.horizontal,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: numRows,
                  childAspectRatio: 0.22,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 16,
                ),
                itemCount: displayApps.length,
                itemBuilder: (context, index) {
                  final app = displayApps[index];
                  return _buildAppCard(responsive, app);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAppCard(ResponsiveHelper responsive, App app) {
    // Get category name
    final categories = context.read<AddAppProvider>().categories;
    final category = categories.firstWhere(
      (c) => c.id == app.category,
      orElse: () => Category(id: app.category, title: app.getCategoryName()),
    );

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _handleAppTap(app),
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
          child: Row(
            children: [
              // App icon - square with rounded corners like mobile
              CachedNetworkImage(
                imageUrl: app.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    image: DecorationImage(
                      image: imageProvider,
                      fit: BoxFit.cover,
                    ),
                  ),
                ),
                placeholder: (context, url) => Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    color: const Color(0xFF35343B),
                  ),
                ),
                errorWidget: (context, url, error) => Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    color: const Color(0xFF35343B),
                  ),
                  child: const Icon(Icons.apps, color: Colors.white54, size: 24),
                ),
              ),

              const SizedBox(width: 12),

              // App info
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // App name
                    Text(
                      app.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                        color: ResponsiveHelper.textPrimary,
                      ),
                    ),

                    const SizedBox(height: 2),

                    // Category
                    Text(
                      category.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        color: ResponsiveHelper.textTertiary,
                      ),
                    ),

                    // Rating
                    if (app.ratingAvg != null) ...[
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          const Icon(
                            Icons.star_rounded,
                            color: ResponsiveHelper.purplePrimary,
                            size: 14,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            app.getRatingAvg()!,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              color: Colors.grey.shade300,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '(${app.ratingCount})',
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.grey.shade500,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),

              const SizedBox(width: 12),

              // Install/Open button - pill shaped like mobile
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: app.enabled ? Colors.grey.shade700 : Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  app.enabled ? 'Open' : 'Install',
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: app.enabled ? Colors.white : Colors.black,
                  ),
                ),
              ),
            ],
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

    // Use vertical list for filtered/searched apps
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final app = apps[index];
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _buildAppCard(responsive, app),
          );
        },
        childCount: apps.length,
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

