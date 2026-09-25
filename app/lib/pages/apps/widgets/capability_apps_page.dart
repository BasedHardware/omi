import 'package:flutter/material.dart';

import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/capability_category_section.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class CapabilityAppsPage extends StatefulWidget {
  final AppCapability capability;
  final List<App> apps;

  const CapabilityAppsPage({super.key, required this.capability, required this.apps});

  @override
  State<CapabilityAppsPage> createState() => _CapabilityAppsPageState();
}

class _CapabilityAppsPageState extends State<CapabilityAppsPage> {
  List<Map<String, dynamic>> _categoryGroups = [];
  bool _isLoading = true;
  bool _loadFailed = false;
  int _totalCount = 0;

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
      final result = await retrieveCapabilityAppsGroupedByCategory(
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
                    decoration: const BoxDecoration(
                      color: OmiColors.surface1,
                      borderRadius: OmiRadius.smAll,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    width: 40,
                    height: 20,
                    decoration: const BoxDecoration(
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
                        decoration: const BoxDecoration(
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
                              decoration: const BoxDecoration(
                                color: OmiColors.surface1,
                                borderRadius: OmiRadius.smAll,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Container(
                              width: 80,
                              height: 12,
                              decoration: const BoxDecoration(
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
                        decoration: const BoxDecoration(
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
  }
}
