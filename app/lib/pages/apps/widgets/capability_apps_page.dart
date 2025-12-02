import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/app_provider.dart';

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
  List<App> _apps = [];
  bool _isLoading = true;
  int _totalCount = 0;

  @override
  void initState() {
    super.initState();
    _apps = widget.apps;
    _totalCount = widget.apps.length;
    _fetchCapabilityApps();
  }

  Future<void> _fetchCapabilityApps() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final result = await retrieveAppsByCapability(
        capability: widget.capability.id,
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
      debugPrint('Error fetching capability apps: $e');
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
        title: Text(
          widget.capability.title,
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
      body: _isLoading && _apps.isEmpty
          ? const Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            )
          : RefreshIndicator(
              onRefresh: _fetchCapabilityApps,
              color: Colors.deepPurpleAccent,
              backgroundColor: Colors.white,
              child: ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: _apps.length,
                separatorBuilder: (context, index) => const SizedBox(height: 8),
                itemBuilder: (context, index) {
                  final app = _apps[index];
                  return Selector<AppProvider, List<App>>(
                    selector: (context, provider) => provider.apps,
                    builder: (context, allApps, child) {
                      final originalIndex = allApps.indexWhere(
                        (appItem) => appItem.id == app.id,
                      );
                      return AppListItem(
                        app: app,
                        index: originalIndex >= 0 ? originalIndex : index,
                      );
                    },
                  );
                },
              ),
            ),
    );
  }
}
