import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/list_item.dart';

class CategoryAppsPage extends StatelessWidget {
  final Category category;
  final List<App> apps;

  const CategoryAppsPage({
    super.key,
    required this.category,
    required this.apps,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(category.title),
        centerTitle: true,
        elevation: 0,
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with count
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Text(
                  '${apps.length} app${apps.length == 1 ? '' : 's'}',
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

          // Apps list
          Expanded(
            child: apps.isEmpty
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
                    itemCount: apps.length,
                    itemBuilder: (context, index) {
                      return AppListItem(
                        app: apps[index],
                        index: index,
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
