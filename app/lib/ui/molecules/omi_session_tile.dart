import 'package:flutter/material.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSessionTile extends AdaptiveWidget {
  final String title;
  final String subtitle;
  final bool isActive;
  final VoidCallback onTap;
  final VoidCallback? onDelete;
  final bool showDeleteButton;

  const OmiSessionTile({
    super.key,
    required this.title,
    required this.subtitle,
    required this.isActive,
    required this.onTap,
    this.onDelete,
    this.showDeleteButton = true,
  });

  @override
  Widget buildDesktop(BuildContext context) => _tile();

  @override
  Widget buildMobile(BuildContext context) => _tile();

  Widget _tile() {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isActive
                  ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.15)
                  : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isActive
                    ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.3)
                    : Colors.transparent,
                width: 1,
              ),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.chat_bubble_outline_rounded,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: isActive
                              ? ResponsiveHelper.purplePrimary
                              : ResponsiveHelper.textPrimary,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: const TextStyle(
                          color: ResponsiveHelper.textTertiary,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                if (showDeleteButton && onDelete != null) ...[
                  const SizedBox(width: 8),
                  // Use different sizes for mobile vs desktop
                  LayoutBuilder(
                    builder: (context, constraints) {
                      // Check if we're on mobile by looking at screen width
                      final isMobile = MediaQuery.of(context).size.width < 600;
                      return OmiIconButton(
                        icon: Icons.delete_outline,
                        onPressed: onDelete!,
                        style: OmiIconButtonStyle.neutral,
                        size: isMobile ? 40 : 24,
                        iconSize: isMobile ? 18 : 14,
                        borderRadius: isMobile ? 8 : 4,
                      );
                    },
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
} 