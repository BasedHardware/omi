import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CategoryAppsPage extends StatefulWidget {
  final Category category;
  final List<App> apps;

  const CategoryAppsPage({super.key, required this.category, required this.apps});

  @override
  State<CategoryAppsPage> createState() => _CategoryAppsPageState();
}

class _CategoryAppsPageState extends State<CategoryAppsPage> {
  List<App> _apps = [];
  bool _isLoading = true;
  bool _loadFailed = false;
  int _totalCount = 0;

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
      final result = await retrieveAppsByCategory(
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
  }
}
