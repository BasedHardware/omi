import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';

class CategoryChip extends StatelessWidget {
  final MemoryCategory category;
  final int? count;
  final bool isSelected;
  final VoidCallback? onTap;
  final bool showIcon;
  final bool showCheckmark;

  const CategoryChip({
    super.key,
    required this.category,
    this.count,
    this.isSelected = false,
    this.onTap,
    this.showIcon = false,
    this.showCheckmark = false,
  });

  Color _getCategoryColor() {
    switch (category) {
      case MemoryCategory.interesting:
        return Colors.blue;
      case MemoryCategory.system:
        return Colors.grey;
    }
  }

  IconData _getCategoryIcon() {
    switch (category) {
      case MemoryCategory.interesting:
        return Icons.star_outline;
      case MemoryCategory.system:
        return Icons.settings_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final categoryName = category.toString().split('.').last;
    // Use shorter display names for categories
    String displayName;
    switch (category) {
      case MemoryCategory.interesting:
        displayName = "Interesting";
        break;
      case MemoryCategory.system:
        displayName = "System";
        break;
    }

    final countText = count != null ? ' ($count)' : '';

    final categoryColor = _getCategoryColor();
    final categoryIcon = _getCategoryIcon();

    Widget chip = Container(
      height: 26,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
      decoration: BoxDecoration(
        color: isSelected
            ? (onTap != null ? categoryColor : categoryColor.withOpacity(0.15))
            : Colors.grey.shade800.withOpacity(0.6),
        borderRadius: BorderRadius.circular(13),
        border: isSelected && onTap == null ? Border.all(color: categoryColor, width: 1) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showIcon) ...[
            Icon(
              categoryIcon,
              size: 14,
              color: isSelected && onTap != null ? Colors.white : categoryColor,
            ),
            const SizedBox(width: 4),
          ],
          if (showCheckmark && isSelected) ...[
            const Icon(Icons.check, size: 12, color: Colors.white),
            const SizedBox(width: 2),
          ],
          Text(
            displayName + countText,
            style: TextStyle(
              color: isSelected ? (onTap != null ? Colors.white : categoryColor) : Colors.white70,
              fontSize: 12,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
        ],
      ),
    );

    if (onTap != null) {
      return GestureDetector(
        onTap: onTap,
        child: chip,
      );
    }

    return Align(
      alignment: Alignment.centerLeft,
      child: chip,
    );
  }
}
