import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/widgets/capability_category_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

class CapabilityAppsPage extends StatefulWidget {
  final AppCapability capability;
  final List<App> apps;

  const CapabilityAppsPage({
    super.key,
    required this.capability,
    required this.apps,
  });

  @override
  State<CapabilityAppsPage> createState() => _CapabilityAppsPageState();
}

class _CapabilityAppsPageState extends State<CapabilityAppsPage> {
  List<Map<String, dynamic>> _categoryGroups = [];
  bool _isLoading = true;
  int _totalCount = 0;

  @override
  void initState() {
    super.initState();
    _groupCapabilityApps();
  }

  void _groupCapabilityApps() {
    setState(() {
      _isLoading = true;
    });

    // Use frontend filtering and grouping instead of backend call
    final appProvider = Provider.of<AppProvider>(context, listen: false);

    // Use all apps from provider, not just widget.apps (which might be pre-filtered)
    // Filter apps by capability
    final filteredApps = appProvider.filterAppsByCapability(appProvider.apps, widget.capability.id);

    // Group filtered apps by category
    final groups = appProvider.groupCapabilityAppsByCategory(filteredApps, widget.capability.id);

    if (mounted) {
      setState(() {
        _categoryGroups = groups;
        _totalCount = filteredApps.length;
        _isLoading = false;
      });
    }
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
                    width: 40,
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

  Widget _buildShimmerView() {
    return SingleChildScrollView(
      physics: const NeverScrollableScrollPhysics(),
      child: Column(
        children: [
          _buildShimmerCategorySection(),
          _buildShimmerCategorySection(),
          _buildShimmerCategorySection(),
          const SizedBox(height: 100),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(
          widget.capability.id == 'chat' ? 'Chat Apps' : widget.capability.title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          if (!_isLoading)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade700,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '$_totalCount apps',
                    style: TextStyle(
                      color: Colors.grey.shade300,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
      body: _isLoading
          ? _buildShimmerView()
          : RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.mediumImpact();
                _groupCapabilityApps();
              },
              color: Colors.deepPurpleAccent,
              backgroundColor: Colors.white,
              child: _totalCount == 0
                  ? Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.apps_outlined,
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
                            'Check back later for new apps',
                            style: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    )
                  : _categoryGroups.isEmpty
                      ? ListView.builder(
                          padding: const EdgeInsets.only(top: 8, bottom: 100),
                          itemCount: 1,
                          itemBuilder: (context, index) {
                            // If no category groups but we have apps, show them all in one group
                            final appProvider = Provider.of<AppProvider>(context, listen: false);
                            final filteredApps =
                                appProvider.filterAppsByCapability(appProvider.apps, widget.capability.id);
                            return CapabilityCategorySection(
                              categoryName: widget.capability.title,
                              apps: filteredApps,
                            );
                          },
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.only(top: 8, bottom: 100),
                          itemCount: _categoryGroups.length,
                          itemBuilder: (context, index) {
                            final group = _categoryGroups[index];
                            final categoryMap = group['category'] as Map<String, dynamic>?;
                            final categoryTitle = categoryMap?['title'] as String? ?? 'Other';
                            final apps = group['data'] as List<App>? ?? [];

                            if (apps.isEmpty) return const SizedBox.shrink();

                            return CapabilityCategorySection(
                              categoryName: categoryTitle,
                              apps: apps,
                            );
                          },
                        ),
            ),
    );
  }
}
