import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/list_item.dart';

class CategoryCard extends StatelessWidget {
  final String title;
  final List<App> apps;
  final double? height;
  const CategoryCard({super.key, required this.title, required this.apps, this.height});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(top: 16.0, left: 10, right: 10),
      height: height ?? MediaQuery.sizeOf(context).height * 0.4,
      margin: const EdgeInsets.only(left: 6.0, right: 6.0, top: 12, bottom: 14),
      decoration: BoxDecoration(
        color: Colors.grey.shade900,
        borderRadius: BorderRadius.circular(16.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8.0),
            child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 18)),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: GridView.builder(
              scrollDirection: Axis.horizontal,
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                childAspectRatio: 0.3,
                crossAxisSpacing: 6,
                mainAxisSpacing: 6,
              ),
              itemCount: apps.length,
              itemBuilder: (context, index) => AppItemCard(
                app: apps[index],
                index: index,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
