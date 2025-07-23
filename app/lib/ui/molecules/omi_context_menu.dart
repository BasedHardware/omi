import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiContextMenuItem {
  final String id;
  final String title;
  final String subtitle;
  final IconData icon;
  final Color iconColor;
  final Color backgroundColor;
  final bool enabled;
  final VoidCallback? onTap;

  const OmiContextMenuItem({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.iconColor,
    required this.backgroundColor,
    this.enabled = true,
    this.onTap,
  });
}

class OmiContextMenu {
  static Future<String?> show(
    BuildContext context, {
    required Offset position,
    required List<OmiContextMenuItem> items,
    bool showDividerBeforeLast = false,
  }) {
    return showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        position.dx,
        position.dy,
        position.dx,
        position.dy,
      ),
      color: ResponsiveHelper.backgroundSecondary,
      surfaceTintColor: Colors.transparent,
      shadowColor: Colors.black.withOpacity(0.3),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          width: 1,
        ),
      ),
      elevation: 12,
      constraints: const BoxConstraints(
        minWidth: 220,
        maxWidth: 280,
      ),
      items: _buildMenuItems(items, showDividerBeforeLast),
    );
  }

  static List<PopupMenuEntry<String>> _buildMenuItems(
    List<OmiContextMenuItem> items,
    bool showDividerBeforeLast,
  ) {
    final List<PopupMenuEntry<String>> menuItems = [];

    for (int i = 0; i < items.length; i++) {
      final item = items[i];

      // Add divider before last item if requested
      if (showDividerBeforeLast && i == items.length - 1 && items.length > 1) {
        menuItems.add(
          PopupMenuItem<String>(
            height: 1,
            enabled: false,
            child: Container(
              height: 1,
              margin: const EdgeInsets.symmetric(horizontal: 8),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    Colors.transparent,
                    ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        );
      }

      menuItems.add(
        PopupMenuItem<String>(
          value: item.id,
          enabled: item.enabled,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          child: Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: item.backgroundColor,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  item.icon,
                  size: 16,
                  color: item.iconColor,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: item.enabled ? ResponsiveHelper.textPrimary : ResponsiveHelper.textTertiary,
                      ),
                    ),
                    Text(
                      item.subtitle,
                      style: const TextStyle(
                        fontSize: 12,
                        color: ResponsiveHelper.textTertiary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    return menuItems;
  }
}
