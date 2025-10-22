import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/app_provider.dart';

class AuthorAppsPage extends StatefulWidget {
  final String authorName;
  final List<App> apps;

  const AuthorAppsPage({
    super.key,
    required this.authorName,
    required this.apps,
  });

  @override
  State<AuthorAppsPage> createState() => _AuthorAppsPageState();
}

class _AuthorAppsPageState extends State<AuthorAppsPage> {
  late List<App> _apps;

  @override
  void initState() {
    super.initState();
    _apps = widget.apps;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Column(
          children: [
            Text(
              'Apps by ${widget.authorName}',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            Text(
              '${_apps.length} app${_apps.length == 1 ? '' : 's'}',
              style: TextStyle(
                color: Colors.grey.shade400,
                fontSize: 12,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: _apps.isEmpty
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
                        Text(
                          'No apps found',
                          style: TextStyle(
                            fontSize: 18,
                            color: Colors.grey.shade400,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'This author hasn\'t published any apps yet',
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
