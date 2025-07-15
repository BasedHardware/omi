import 'package:flutter/material.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Standard icon + title header row used across pages (action items, overviews, etc.)
class OmiSectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? badgeLabel; // optional trailing grey-pill count or text
  final double spacing;

  const OmiSectionHeader({
    super.key,
    required this.icon,
    required this.title,
    this.badgeLabel,
    this.spacing = 8,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        OmiIconButton(
          icon: icon,
          style: OmiIconButtonStyle.neutral,
          size: 24,
          iconSize: 12,
          borderRadius: 6,
          onPressed: null,
        ),
        SizedBox(width: spacing),
        Text(
          title,
          style: const TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        if (badgeLabel != null) ...[
          SizedBox(width: spacing),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              badgeLabel!,
              style: const TextStyle(
                color: ResponsiveHelper.textTertiary,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ]
      ],
    );
  }
}
