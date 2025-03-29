import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/extensions/string.dart';

import 'delete_confirmation.dart';

class MemoryItem extends StatelessWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final Function(BuildContext, Memory, MemoriesProvider) onTap;
  final bool showDismissible;

  const MemoryItem({
    super.key,
    required this.memory,
    required this.provider,
    required this.onTap,
    this.showDismissible = true,
  });

  @override
  Widget build(BuildContext context) {
    final Widget memoryWidget = GestureDetector(
      onTap: () => onTap(context, memory, provider),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              contentPadding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              title: Text(
                memory.content.decodeString,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
              ),
              trailing: _buildVisibilityButton(context),
            ),
          ],
        ),
      ),
    );

    if (!showDismissible) {
      return memoryWidget;
    }

    return Dismissible(
      key: Key(memory.id),
      direction: DismissDirection.endToStart,
      confirmDismiss: (direction) async {
        final shouldDelete = await DeleteConfirmation.show(context);
        return shouldDelete;
      },
      onDismissed: (direction) {
        provider.deleteMemory(memory);
        MixpanelManager().memoriesPageDeletedMemory(memory);
      },
      background: Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: BoxDecoration(
          color: Colors.red.shade900,
          borderRadius: BorderRadius.circular(12),
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: memoryWidget,
    );
  }

  Widget _buildVisibilityButton(BuildContext context) {
    return PopupMenuButton<MemoryVisibility>(
      padding: EdgeInsets.zero,
      position: PopupMenuPosition.under,
      surfaceTintColor: Colors.transparent,
      color: Colors.grey.shade800,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
      ),
      offset: const Offset(0, 4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              memory.visibility == MemoryVisibility.private ? Icons.lock_outline : Icons.public,
              size: 16,
              color: Colors.white70,
            ),
            const SizedBox(width: 4),
            const Icon(
              Icons.keyboard_arrow_down,
              size: 16,
              color: Colors.white70,
            ),
          ],
        ),
      ),
      itemBuilder: (context) => [
        _buildVisibilityItem(
          context,
          MemoryVisibility.private,
          Icons.lock_outline,
          'Will not be used for personas',
        ),
        _buildVisibilityItem(
          context,
          MemoryVisibility.public,
          Icons.public,
          'Will be used for personas',
        ),
      ],
      onSelected: (visibility) {
        provider.updateMemoryVisibility(memory, visibility);
      },
    );
  }

  PopupMenuItem<MemoryVisibility> _buildVisibilityItem(
    BuildContext context,
    MemoryVisibility visibility,
    IconData icon,
    String description,
  ) {
    final isSelected = memory.visibility == visibility;
    return PopupMenuItem<MemoryVisibility>(
      value: visibility,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Icon(
              icon,
              size: 18,
              color: isSelected ? Colors.white : Colors.white70,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    visibility.name[0].toUpperCase() + visibility.name.substring(1),
                    style: TextStyle(
                      color: isSelected ? Colors.white : Colors.white70,
                      fontSize: 14,
                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    description,
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            if (isSelected)
              const Icon(
                Icons.check,
                size: 18,
                color: Colors.white,
              ),
          ],
        ),
      ),
    );
  }
}
