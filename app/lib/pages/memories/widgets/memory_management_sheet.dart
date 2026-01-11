import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/utils/l10n_extensions.dart';

class MemoryManagementSheet extends StatelessWidget {
  final MemoriesProvider provider;

  const MemoryManagementSheet({
    super.key,
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, child) {
        return Container(
          decoration: BoxDecoration(
            color: AppStyles.backgroundSecondary,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildHeader(context),
                const Divider(height: 1, color: Colors.white10),
                _buildFilterSection(context),
                const Divider(height: 1, color: Colors.white10),
                _buildMemoryCount(context),
                _buildActionButtons(context),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 16, 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            context.l10n.memoryManagement,
            style: AppStyles.subtitle,
          ),
          IconButton(
            icon: const Icon(Icons.close, color: Colors.white70),
            onPressed: () => Navigator.pop(context),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 16, 8),
          child: Text(context.l10n.filterMemories, style: AppStyles.title),
        ),
        _buildFilterOption(context, context.l10n.filterAll, null),
        _buildFilterOption(context, context.l10n.filterSystem, MemoryCategory.system),
        _buildFilterOption(context, context.l10n.filterInteresting, MemoryCategory.interesting),
        _buildFilterOption(context, context.l10n.filterManual, MemoryCategory.manual),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildFilterOption(BuildContext context, String label, MemoryCategory? category) {
    // If category is null, it represents "All"
    // For "All", it is selected if the set is empty.
    final bool isSelected;
    if (category == null) {
      isSelected = provider.selectedCategories.isEmpty;
    } else {
      isSelected = provider.selectedCategories.contains(category);
    }

    return InkWell(
      onTap: () {
        if (category == null) {
          provider.clearCategoryFilter();
        } else {
          provider.toggleCategoryFilter(category);
        }
        // Do NOT pop here to allow multiple selections
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        child: Row(
          children: [
            Text(
              label,
              style: TextStyle(
                color: isSelected ? Colors.purpleAccent : Colors.white,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                fontSize: 16,
              ),
            ),
            const Spacer(),
            if (isSelected) const Icon(Icons.check, color: Colors.purpleAccent, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildMemoryCount(BuildContext context) {
    final totalMemories = provider.memories.length;
    final publicMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'public').length;
    final privateMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'private').length;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.totalMemoriesCount(totalMemories),
            style: AppStyles.body,
          ),
          const SizedBox(height: 8),
          _buildMemoryCountRow(Icons.public, context.l10n.publicMemories, publicMemories),
          const SizedBox(height: 4),
          _buildMemoryCountRow(Icons.lock_outline, context.l10n.privateMemories, privateMemories),
        ],
      ),
    );
  }

  Widget _buildMemoryCountRow(IconData icon, String label, int count) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Colors.white60),
        const SizedBox(width: 8),
        Text(
          label,
          style: AppStyles.caption,
        ),
        const Spacer(),
        Text(
          count.toString(),
          style: AppStyles.caption.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _buildActionButtons(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildActionButton(
            context,
            context.l10n.makeAllPrivate,
            Icons.lock_outline,
            Colors.white.withOpacity(0.1),
            () => _makeAllMemoriesPrivate(context),
          ),
          const SizedBox(height: 12),
          _buildActionButton(
            context,
            context.l10n.makeAllPublic,
            Icons.public,
            Colors.white.withOpacity(0.1),
            () => _makeAllMemoriesPublic(context),
          ),
          const SizedBox(height: 24),
          const Divider(height: 1, color: Colors.white10),
          const SizedBox(height: 24),
          _buildActionButton(
            context,
            context.l10n.deleteAllMemories,
            Icons.delete_outline,
            Colors.red.withOpacity(0.1),
            () => _confirmDeleteAllMemories(context),
            textColor: Colors.red,
            iconColor: Colors.red,
          ),
          const SizedBox(height: 12),
        ],
      ),
    );
  }

  Widget _buildActionButton(
    BuildContext context,
    String text,
    IconData icon,
    Color backgroundColor,
    VoidCallback onPressed, {
    Color textColor = Colors.white,
    Color iconColor = Colors.white,
  }) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: backgroundColor,
        foregroundColor: textColor,
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: iconColor),
          const SizedBox(width: 12),
          Text(
            text,
            style: TextStyle(
              color: textColor,
              fontSize: 15,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  void _makeAllMemoriesPrivate(BuildContext context) async {
    Navigator.pop(context);
    await provider.updateAllMemoriesVisibility(true);

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.allMemoriesPrivateResult),
          backgroundColor: AppStyles.backgroundTertiary,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _makeAllMemoriesPublic(BuildContext context) async {
    Navigator.pop(context);
    await provider.updateAllMemoriesVisibility(false);

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.allMemoriesPublicResult),
          backgroundColor: AppStyles.backgroundTertiary,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _confirmDeleteAllMemories(BuildContext context) {
    if (provider.memories.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.noMemoriesToDelete),
          backgroundColor: AppStyles.backgroundTertiary,
          duration: const Duration(seconds: 2),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        ),
      );
      Navigator.pop(context);
      return;
    }

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppStyles.backgroundSecondary,
        title: Text(
          context.l10n.clearMemoryTitle,
          style: const TextStyle(color: Colors.white),
        ),
        content: Text(
          context.l10n.clearMemoryMessage,
          style: TextStyle(color: Colors.grey.shade300),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              context.l10n.cancel,
              style: TextStyle(color: Colors.grey.shade400),
            ),
          ),
          TextButton(
            onPressed: () {
              provider.deleteAllMemories();
              Navigator.pop(context); // Close dialog
              Navigator.pop(context); // Close sheet
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(context.l10n.memoryClearedSuccess),
                  backgroundColor: AppStyles.backgroundTertiary,
                  duration: const Duration(seconds: 2),
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                  margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                ),
              );
            },
            child: Text(
              context.l10n.clearMemoryButton,
              style: const TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
