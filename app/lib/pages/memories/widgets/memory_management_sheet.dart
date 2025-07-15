import 'package:flutter/material.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/ui_guidelines.dart';

class MemoryManagementSheet extends StatelessWidget {
  final MemoriesProvider provider;

  const MemoryManagementSheet({
    super.key,
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
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
            _buildMemoryCount(context),
            _buildActionButtons(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 16, 16, 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            'Memory Management',
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
            'You have $totalMemories total memories',
            style: AppStyles.body,
          ),
          const SizedBox(height: 8),
          _buildMemoryCountRow(Icons.public, 'Public memories', publicMemories),
          const SizedBox(height: 4),
          _buildMemoryCountRow(Icons.lock_outline, 'Private memories', privateMemories),
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
            'Make All Memories Private',
            Icons.lock_outline,
            Colors.white.withOpacity(0.1),
            () => _makeAllMemoriesPrivate(context),
          ),
          const SizedBox(height: 12),
          _buildActionButton(
            context,
            'Make All Memories Public',
            Icons.public,
            Colors.white.withOpacity(0.1),
            () => _makeAllMemoriesPublic(context),
          ),
          const SizedBox(height: 24),
          const Divider(height: 1, color: Colors.white10),
          const SizedBox(height: 24),
          _buildActionButton(
            context,
            'Delete All Memories',
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
          content: const Text('All memories are now private'),
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
          content: const Text('All memories are now public'),
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
          content: const Text('No memories to delete'),
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
        title: const Text(
          'Clear Omi\'s Memory',
          style: TextStyle(color: Colors.white),
        ),
        content: Text(
          'Are you sure you want to clear Omi\'s memory? This action cannot be undone.',
          style: TextStyle(color: Colors.grey.shade300),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'Cancel',
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
                  content: const Text('Omi\'s memory about you has been cleared'),
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
            child: const Text(
              'Clear Memory',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
