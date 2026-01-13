import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/ui/atoms/omi_icon_badge.dart';
import 'package:omi/ui/molecules/omi_popup_menu.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';

class DesktopMemoryItem extends StatelessWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final Function(BuildContext, Memory, MemoriesProvider) onTap;

  const DesktopMemoryItem({
    super.key,
    required this.memory,
    required this.provider,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            if (memory.isLocked) {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (context) => const UsagePage(showUpgradeDialog: true),
                ),
              );
              return;
            }
            onTap(context, memory, provider);
          },
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.05),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Category icon
                OmiIconBadge(
                  icon: _getCategoryIcon(),
                  bgColor: _getCategoryColor().withValues(alpha: 0.2),
                  iconColor: _getCategoryColor(),
                  iconSize: 16,
                  radius: 8,
                  padding: const EdgeInsets.all(8),
                ),

                const SizedBox(width: 12),

                // Memory content
                Expanded(
                  child: Stack(
                    children: [
                      Text(
                        memory.content.decodeString,
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 15,
                          height: 1.4,
                        ),
                      ),
                      if (memory.isLocked) _buildLockedOverlay(context),
                    ],
                  ),
                ),

                const SizedBox(width: 12),

                _buildVisibilityIndicator(),

                const SizedBox(width: 8),

                _buildQuickActions(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLockedOverlay(BuildContext context) {
    return Positioned.fill(
      child: ClipRRect(
        borderRadius: const BorderRadius.all(Radius.circular(8)),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 2.0, sigmaY: 2.0),
          child: Container(
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.01),
            ),
            child: const Text(
              'Upgrade to unlimited',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildVisibilityIndicator() {
    return OmiIconBadge(
      icon: memory.visibility == MemoryVisibility.private ? Icons.lock_outline : Icons.public,
      bgColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
      iconColor: ResponsiveHelper.textTertiary,
      iconSize: 14,
      radius: 6,
      padding: const EdgeInsets.all(6),
    );
  }

  Widget _buildQuickActions() {
    return Builder(
      builder: (context) => OmiPopupMenuButton<String>(
        icon: Icons.more_vert,
        itemBuilder: (context) => [
          const PopupMenuItem<String>(
            value: 'edit',
            child: Row(
              children: [
                Icon(
                  Icons.edit_outlined,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                SizedBox(width: 8),
                Text(
                  'Edit',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          PopupMenuItem<String>(
            value: 'visibility',
            child: Row(
              children: [
                Icon(
                  memory.visibility == MemoryVisibility.private ? Icons.public : Icons.lock_outline,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  memory.visibility == MemoryVisibility.private ? 'Make Public' : 'Make Private',
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          PopupMenuItem<String>(
            value: 'delete',
            child: Row(
              children: [
                Icon(
                  Icons.delete_outline,
                  color: Colors.red.shade400,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  'Delete',
                  style: TextStyle(
                    color: Colors.red.shade400,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
        onSelected: (value) => _handleMenuSelection(value, context),
      ),
    );
  }

  void _handleMenuSelection(String value, BuildContext context) {
    switch (value) {
      case 'edit':
        onTap(context, memory, provider);
        break;
      case 'visibility':
        final newVisibility =
            memory.visibility == MemoryVisibility.private ? MemoryVisibility.public : MemoryVisibility.private;
        provider.updateMemoryVisibility(memory, newVisibility);
        MixpanelManager().memoryVisibilityChanged(memory, newVisibility);
        break;
      case 'delete':
        OmiConfirmDialog.show(
          context,
          title: 'Delete Memory',
          message: 'Are you sure you want to delete this memory? This action cannot be undone.',
        ).then((confirmed) {
          if (confirmed == true) {
            provider.deleteMemory(memory);
            MixpanelManager().memoriesPageDeletedMemory(memory);
          }
        });
        break;
    }
  }

  Color _getCategoryColor() {
    switch (memory.category) {
      case MemoryCategory.system:
        return ResponsiveHelper.purplePrimary;
      case MemoryCategory.interesting:
        return Colors.amber;
      case MemoryCategory.manual:
        return Colors.purple;
    }
  }

  IconData _getCategoryIcon() {
    switch (memory.category) {
      case MemoryCategory.system:
        return Icons.person_outlined;
      case MemoryCategory.interesting:
        return Icons.lightbulb_outlined;
      case MemoryCategory.manual:
        return Icons.edit_outlined;
    }
  }
}

extension StringCapitalize on String {
  String capitalize() {
    if (isEmpty) return this;
    return this[0].toUpperCase() + substring(1);
  }
}
