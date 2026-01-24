import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

class CategoryAppsPage extends StatefulWidget {
  final Category category;
  final List<App> apps;

  const CategoryAppsPage({
    super.key,
    required this.category,
    required this.apps,
  });

  @override
  State<CategoryAppsPage> createState() => _CategoryAppsPageState();
}

class _CategoryAppsPageState extends State<CategoryAppsPage> {
  List<App> _apps = [];
  bool _isLoading = true;
  int _totalCount = 0;

  @override
  void initState() {
    super.initState();
    _apps = widget.apps;
    _totalCount = widget.apps.length;

    // Track category page opened
    MixpanelManager().appsCategoryPageOpened(
      category: widget.category.title,
      appCount: widget.apps.length,
    );

    _fetchCategoryApps();
  }

  Future<void> _fetchCategoryApps() async {
    setState(() {
      _isLoading = true;
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
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(widget.category.title),
        centerTitle: true,
        elevation: 0,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Text(
                  _isLoading ? '' : '$_totalCount app${_totalCount == 1 ? '' : 's'}',
                  style: TextStyle(
                    fontSize: 16,
                    color: Colors.grey.shade400,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const Spacer(),
              ],
            ),
          ),
          Expanded(
            child: _isLoading
                ? const Center(
                    child: CircularProgressIndicator(
                      color: Colors.deepPurpleAccent,
                    ),
                  )
                : _apps.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.folder_open_outlined,
                              size: 64,
                              color: Colors.grey.shade600,
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'No apps in this category yet',
                              style: TextStyle(
                                fontSize: 18,
                                color: Colors.grey.shade400,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'Check back later for new apps',
                              style: TextStyle(
                                fontSize: 14,
                                color: Colors.grey.shade500,
                              ),
                            ),
                          ],
                        ),
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        itemCount: _apps.length,
                        itemBuilder: (context, index) {
                          final app = _apps[index];
                          final allApps = context.read<AppProvider>().apps;
                          final originalIndex = allApps.indexWhere((a) => a.id == app.id);

                          return AppListItem(
                            app: app,
                            index: originalIndex >= 0 ? originalIndex : index,
                          );
                        },
                        separatorBuilder: (context, index) => const SizedBox(height: 8),
                      ),
          ),
        ],
      ),
    );
  }
}
