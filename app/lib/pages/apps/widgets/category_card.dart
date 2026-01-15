import 'package:flutter/material.dart';

import 'package:omi/backend/schema/app.dart';

class CategoryCard extends StatelessWidget {
  final Category category;
  final int appCount;
  final VoidCallback onTap;

  const CategoryCard({
    super.key,
    required this.category,
    required this.appCount,
    required this.onTap,
  });

  IconData _getCategoryIcon(String categoryId) {
    switch (categoryId.toLowerCase()) {
      case 'productivity':
        return Icons.work_outline;
      case 'health':
        return Icons.health_and_safety_outlined;
      case 'entertainment':
        return Icons.movie_outlined;
      case 'education':
        return Icons.school_outlined;
      case 'social':
        return Icons.people_outline;
      case 'finance':
        return Icons.attach_money_outlined;
      case 'utilities':
        return Icons.build_outlined;
      case 'lifestyle':
        return Icons.home_outlined;
      case 'travel':
        return Icons.flight_takeoff_outlined;
      case 'food':
        return Icons.restaurant_outlined;
      case 'shopping':
        return Icons.shopping_bag_outlined;
      case 'business':
        return Icons.business_outlined;
      case 'communication':
        return Icons.chat_bubble_outline;
      case 'news':
        return Icons.article_outlined;
      case 'sports':
        return Icons.sports_soccer_outlined;
      case 'music':
        return Icons.music_note_outlined;
      case 'photo':
        return Icons.photo_camera_outlined;
      case 'gaming':
        return Icons.sports_esports_outlined;
      default:
        return Icons.folder_outlined;
    }
  }

  Color _getCategoryColor(String categoryId) {
    switch (categoryId.toLowerCase()) {
      case 'productivity':
        return Colors.blue;
      case 'health':
        return Colors.green;
      case 'entertainment':
        return Colors.purple;
      case 'education':
        return Colors.orange;
      case 'social':
        return Colors.pink;
      case 'finance':
        return Colors.teal;
      case 'utilities':
        return Colors.grey;
      case 'lifestyle':
        return Colors.indigo;
      case 'travel':
        return Colors.cyan;
      case 'food':
        return Colors.red;
      case 'shopping':
        return Colors.amber;
      case 'business':
        return Colors.blueGrey;
      case 'communication':
        return Colors.lightBlue;
      case 'news':
        return Colors.deepOrange;
      case 'sports':
        return Colors.lime;
      case 'music':
        return Colors.deepPurple;
      case 'photo':
        return Colors.brown;
      case 'gaming':
        return Colors.lightGreen;
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    final categoryColor = _getCategoryColor(category.id);
    final categoryIcon = _getCategoryIcon(category.id);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25).withOpacity(0.3),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: categoryColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Icon(
                  categoryIcon,
                  size: 28,
                  color: categoryColor,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                category.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 6),
              Text(
                '$appCount app${appCount == 1 ? '' : 's'}',
                style: TextStyle(
                  fontSize: 13,
                  color: Colors.grey.shade400,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
