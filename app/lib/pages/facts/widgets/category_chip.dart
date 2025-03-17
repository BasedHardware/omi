import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';

class CategoryChip extends StatelessWidget {
  final FactCategory category;
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

  @override
  Widget build(BuildContext context) {
    final categoryName = category.toString().split('.').last;
    final displayName = count != null ? '$categoryName ($count)' : categoryName;

    Widget chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: isSelected ? (onTap != null ? Colors.white : Colors.white.withOpacity(0.1)) : Colors.grey.shade800,
        borderRadius: BorderRadius.circular(16),
        border: isSelected && onTap == null ? Border.all(color: Colors.white, width: 1) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showIcon) ...[
            const Icon(Icons.label_outline, size: 14, color: Colors.white),
            const SizedBox(width: 4),
          ],
          if (showCheckmark && isSelected) ...[
            const Icon(Icons.check, size: 14, color: Colors.white),
            const SizedBox(width: 4),
          ],
          Text(
            displayName,
            style: TextStyle(
              color: isSelected ? (onTap != null ? Colors.black : Colors.white) : Colors.white70,
              fontSize: 13,
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

    return chip;
  }
}
