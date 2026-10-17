import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/pages/apps/widgets/capability_category_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Loads a capability's apps grouped by category; [retrieveCapabilityAppsGroupedByCategory] is the owner.
typedef CapabilityAppsLoader
    = Future<({List<Map<String, dynamic>> groups, Map<String, dynamic>? capability, int totalApps})> Function(
        String capability);

class CapabilityAppsPage extends StatefulWidget {
  final AppCapability capability;
  final List<App> apps;

  /// Replaces the HTTP loader in tests; null uses [retrieveCapabilityAppsGroupedByCategory].
  @visibleForTesting
  final CapabilityAppsLoader? loadApps;

  const CapabilityAppsPage({super.key, required this.capability, required this.apps, this.loadApps});

  @override
  State<CapabilityAppsPage> createState() => _CapabilityAppsPageState();
}

class _CapabilityAppsPageState extends State<CapabilityAppsPage> {
  List<Map<String, dynamic>> _categoryGroups = [];
  bool _isLoading = true;
  bool _loadFailed = false;
  int _totalCount = 0;

  /// Apps the native rows are enabling; their Enable option is withdrawn until the owner answers.
  final _enabling = <String>{};

  @override
  void initState() {
    super.initState();
    _loadCapabilityApps();
  }

  Future<void> _loadCapabilityApps() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });

    try {
      // Fetch capability apps grouped by category from backend
      final loader = widget.loadApps;
      final result = loader != null
          ? await loader(widget.capability.id)
          : await retrieveCapabilityAppsGroupedByCategory(
              capability: widget.capability.id,
              includeReviews: true,
            );

      if (mounted) {
        setState(() {
          _categoryGroups = result.groups;
          _totalCount = result.totalApps;
          _isLoading = false;
        });
      }
    } catch (e) {
      Logger.debug('Error loading capability apps: $e');
      if (mounted) {
        setState(() {
          _categoryGroups = [];
          _totalCount = 0;
          _isLoading = false;
          _loadFailed = true;
        });
      }
    }
  }

  Widget _buildShimmerCategorySection() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface2,
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
                      color: OmiColors.surface1,
                      borderRadius: OmiRadius.smAll,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    width: 40,
                    height: 20,
                    decoration: BoxDecoration(
                      color: OmiColors.surface1,
                      borderRadius: OmiRadius.smAll,
                    ),
                  ),
                ],
              ),
            ),
            // Apps grid shimmer
            Container(
              height: 270,
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: GridView.builder(
                scrollDirection: Axis.horizontal,
                physics: const NeverScrollableScrollPhysics(),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 3,
                  childAspectRatio: 0.28,
                  crossAxisSpacing: 0.0,
                  mainAxisSpacing: 14.0,
                ),
                itemCount: 9,
                itemBuilder: (context, index) => Container(
                  padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 4.0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Container(
                        width: 60,
                        height: 60,
                        decoration: BoxDecoration(
                          color: OmiColors.surface1,
                          borderRadius: OmiRadius.smAll,
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
                                color: OmiColors.surface1,
                                borderRadius: OmiRadius.smAll,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Container(
                              width: 80,
                              height: 12,
                              decoration: BoxDecoration(
                                color: OmiColors.surface1,
                                borderRadius: OmiRadius.smAll,
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
                          color: OmiColors.surface1,
                          borderRadius: OmiRadius.pillAll,
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

  Widget _buildShimmerView() {
    return SingleChildScrollView(
      physics: const NeverScrollableScrollPhysics(),
      child: Column(
        children: [...List.generate(3, (_) => _buildShimmerCategorySection()), const SizedBox(height: 100)],
      ),
    );
  }

  /// A page-filling message that still lets pull-to-refresh reach the loader.
  Widget _buildScrollableState(Widget state) {
    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [SliverFillRemaining(hasScrollBody: false, child: state)],
    );
  }

  Widget _buildContent() {
    if (_totalCount == 0 && _loadFailed) {
      return _buildScrollableState(
        OmiErrorState(message: context.l10n.unableToLoadApps, onRetry: _loadCapabilityApps),
      );
    }
    if (_totalCount == 0) {
      return _buildScrollableState(
        OmiEmptyState(
          icon: Icons.apps_outlined,
          title: context.l10n.noAppsFound,
          message: context.l10n.checkBackLaterForNewApps,
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: 100),
      itemCount: _categoryGroups.length,
      itemBuilder: (context, index) {
        final group = _categoryGroups[index];
        final categoryMap = group['category'] as Map<String, dynamic>?;
        final categoryTitle = Category(
          id: categoryMap?['id'] as String? ?? '',
          title: categoryMap?['title'] as String? ?? context.l10n.categoryOther,
        ).getLocalizedTitle(context);
        final apps = group['data'] as List<App>? ?? [];

        if (apps.isEmpty) return const SizedBox.shrink();

        return CapabilityCategorySection(categoryName: categoryTitle, apps: apps);
      },
    );
  }

  String _groupTitle(Map<String, dynamic> group) {
    final categoryMap = group['category'] as Map<String, dynamic>?;
    return Category(
      id: categoryMap?['id'] as String? ?? '',
      title: categoryMap?['title'] as String? ?? context.l10n.categoryOther,
    ).getLocalizedTitle(context);
  }

  Future<void> _openDetail(App app) async {
    PlatformManager.instance.analytics.pageOpened('App Detail');
    final appProvider = context.read<AppProvider>();
    await routeToPage(context, AppDetailPage(app: app));
    appProvider.filterApps();
  }

  /// The row button's Enable: the same consent question and enable owner.
  Future<void> _enable(App app) async {
    final provider = context.read<AppProvider>();
    if (!await confirmAppDataAccess(context, app)) return;
    if (!mounted || !_enabling.add(app.id)) return;
    setState(() {});
    try {
      await provider.toggleApp(app.id, true, null);
    } finally {
      _enabling.remove(app.id);
      if (mounted) setState(() {});
    }
  }

  /// The same states and groups in the native presentation; loading and navigation stay here.
  Widget _native(Widget classic) {
    final l10n = context.l10n;
    final provider = context.watch<AppProvider>();
    final failed = !_isLoading && _totalCount == 0 && _loadFailed;
    NativeRow appRow(App app, String id) {
      final enabled = (provider.apps.firstWhereOrNull((a) => a.id == app.id) ?? app).enabled;
      final canEnable = !enabled && !appNeedsDetailToEnable(app) && !_enabling.contains(app.id);
      return NativeRow(id, app.name.decodeString,
          kind: 'navigation',
          imageUri: nativeImageUri(app.getImageUrl()),
          subtitle: [
            if (_enabling.contains(app.id)) l10n.pleaseWait,
            if (app.description.isNotEmpty) app.description,
            if (app.ratingAvg != null) '★ ${app.getRatingAvg()} (${app.ratingCount})',
          ].join('\n'),
          options: canEnable ? {'enable': l10n.enable} : const {},
          swipeTrailing: canEnable ? const ['enable'] : const [],
          action: (value) => value == 'enable' ? _enable(app) : _openDetail(app));
    }

    return IosNativeSurface(
      title: widget.capability.getLocalizedTitle(context),
      fallback: classic,
      loading: _isLoading,
      failed: failed,
      errorMessage: l10n.unableToLoadApps,
      empty: l10n.noAppsFound,
      onRefresh: (_) async {
        OmiHaptics.medium();
        await _loadCapabilityApps();
      },
      toolbar: [
        NativeRow('capability_apps_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        if (!_isLoading && !failed && _totalCount == 0)
          NativeSection('capability_apps_status', [
            NativeRow('capability_apps_empty', l10n.noAppsFound,
                kind: 'label', symbol: 'square.grid.2x2', subtitle: l10n.checkBackLaterForNewApps),
          ]),
        if (!_isLoading && _totalCount > 0)
          for (final (index, group) in _categoryGroups.indexed)
            if ((group['data'] as List<App>? ?? const <App>[]) case final apps when apps.isNotEmpty)
              NativeSection(
                'group_$index',
                [for (final (row, app) in apps.indexed) appRow(app, 'group_${index}_$row')],
                title: _groupTitle(group),
                footer: l10n.categoryAppCount(apps.length),
              ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        backgroundColor: OmiColors.surface0,
        leading: const OmiBackButton(),
        title: Text(widget.capability.getLocalizedTitle(context)),
      ),
      body: _isLoading
          ? _buildShimmerView()
          : RefreshIndicator(
              onRefresh: () async {
                OmiHaptics.medium();
                await _loadCapabilityApps();
              },
              // The arc is drawn on backgroundColor, so it must not also be white.
              color: OmiColors.onAccent,
              backgroundColor: OmiColors.accent,
              child: _buildContent(),
            ),
    );
    if (!nativePresentationEnabled) return classic;
    return _native(classic);
  }
}
