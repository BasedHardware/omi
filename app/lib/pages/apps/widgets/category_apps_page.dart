import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Loads a category's first page of apps; [retrieveAppsByCategory] is the owner.
typedef CategoryAppsLoader = Future<({List<App> apps, Map<String, dynamic> pagination, Map<String, dynamic>? category})>
    Function(String category);

class CategoryAppsPage extends StatefulWidget {
  final Category category;
  final List<App> apps;

  /// Replaces the HTTP loader in tests; null uses [retrieveAppsByCategory].
  @visibleForTesting
  final CategoryAppsLoader? loadApps;

  const CategoryAppsPage({super.key, required this.category, required this.apps, this.loadApps});

  @override
  State<CategoryAppsPage> createState() => _CategoryAppsPageState();
}

class _CategoryAppsPageState extends State<CategoryAppsPage> {
  List<App> _apps = [];
  bool _isLoading = true;
  bool _loadFailed = false;
  int _totalCount = 0;

  /// Apps the native rows are enabling; their Enable option is withdrawn until the owner answers.
  final _enabling = <String>{};

  @override
  void initState() {
    super.initState();
    _apps = widget.apps;
    _totalCount = widget.apps.length;

    // Track category page opened
    PlatformManager.instance.analytics.appsCategoryPageOpened(
      category: widget.category.title,
      appCount: widget.apps.length,
    );

    _fetchCategoryApps();
  }

  Future<void> _fetchCategoryApps() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });

    try {
      final loader = widget.loadApps;
      final result = loader != null
          ? await loader(widget.category.id)
          : await retrieveAppsByCategory(
              category: widget.category.id,
              offset: 0,
              limit: 50,
              includeReviews: true,
            );

      if (mounted) {
        setState(() {
          _apps = result.apps;
          _totalCount = result.pagination['total'] as int? ?? result.apps.length;
          _isLoading = false;
        });
      }
    } catch (e) {
      Logger.debug('Error fetching category apps: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
          _loadFailed = true;
        });
      }
    }
  }

  Widget _buildBody() {
    if (_isLoading) return const OmiLoadingState();
    // The apps handed in from the store stay on screen if the refresh fails; only an empty page
    // offers Try Again.
    if (_apps.isEmpty && _loadFailed) {
      return OmiErrorState(message: context.l10n.unableToLoadApps, onRetry: _fetchCategoryApps);
    }
    if (_apps.isEmpty) {
      return OmiEmptyState(
        icon: Icons.folder_open_outlined,
        title: context.l10n.noAppsInCategoryYet,
        message: context.l10n.checkBackLaterForNewApps,
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
      itemCount: _apps.length,
      itemBuilder: (context, index) {
        final app = _apps[index];
        final allApps = context.read<AppProvider>().apps;
        final originalIndex = allApps.indexWhere((a) => a.id == app.id);

        return AppListItem(app: app, index: originalIndex >= 0 ? originalIndex : index);
      },
      separatorBuilder: (context, index) => const SizedBox(height: OmiSpacing.xs),
    );
  }

  Future<void> _openDetail(App app) async {
    PlatformManager.instance.analytics.pageOpened('App Detail');
    await routeToPage(context, AppDetailPage(app: app));
  }

  /// The row button's Enable: the same consent question and enable owner.
  Future<void> _enable(App app, int index) async {
    final provider = context.read<AppProvider>();
    if (!await confirmAppDataAccess(context, app)) return;
    if (!mounted || !_enabling.add(app.id)) return;
    setState(() {});
    try {
      await provider.toggleApp(app.id, true, index);
    } finally {
      _enabling.remove(app.id);
      if (mounted) setState(() {});
    }
  }

  /// The same states and list in the native presentation; loading and navigation stay here.
  Widget _native(Widget classic) {
    final l10n = context.l10n;
    final provider = context.watch<AppProvider>();
    final failed = !_isLoading && _apps.isEmpty && _loadFailed;
    NativeRow appRow(App app, int index) {
      final originalIndex = provider.apps.indexWhere((a) => a.id == app.id);
      final enabled = (provider.apps.firstWhereOrNull((a) => a.id == app.id) ?? app).enabled;
      final canEnable = !enabled && !appNeedsDetailToEnable(app) && !_enabling.contains(app.id);
      return NativeRow('apps_$index', app.name.decodeString + (app.private ? ' 🔒'.decodeString : ''),
          kind: 'navigation',
          imageUri: nativeImageUri(app.getImageUrl()),
          subtitle: [
            if (app.description.isNotEmpty) app.description,
            if (app.ratingAvg != null) '★ ${app.getRatingAvg()} (${app.ratingCount})',
          ].join('\n'),
          options: canEnable ? {'enable': l10n.enable} : const {},
          swipeTrailing: canEnable ? const ['enable'] : const [],
          action: (value) =>
              value == 'enable' ? _enable(app, originalIndex >= 0 ? originalIndex : index) : _openDetail(app));
    }

    return IosNativeSurface(
      title: widget.category.getLocalizedTitle(context),
      fallback: classic,
      loading: _isLoading,
      failed: failed,
      errorMessage: l10n.unableToLoadApps,
      empty: l10n.noAppsInCategoryYet,
      onRefresh: (_) => _fetchCategoryApps(),
      toolbar: [
        NativeRow('category_apps_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        if (!_isLoading && !failed)
          NativeSection(
            'category_apps',
            [
              if (_apps.isEmpty)
                NativeRow('category_apps_empty', l10n.noAppsInCategoryYet,
                    kind: 'label', symbol: 'folder', subtitle: l10n.checkBackLaterForNewApps),
              for (final (index, app) in _apps.indexed) appRow(app, index),
            ],
            title: l10n.categoryAppCount(_totalCount),
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
        title: Text(widget.category.getLocalizedTitle(context)),
        centerTitle: true,
        elevation: 0,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(OmiSpacing.md),
            child: Text(
              _isLoading || (_apps.isEmpty && _loadFailed) ? '' : context.l10n.categoryAppCount(_totalCount),
              style: OmiType.callout.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
            ),
          ),
          Expanded(child: _buildBody()),
        ],
      ),
    );
    if (!nativePresentationEnabled) return classic;
    return _native(classic);
  }
}
