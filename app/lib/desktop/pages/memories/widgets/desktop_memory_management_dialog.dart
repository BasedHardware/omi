import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';

class DesktopMemoryManagementDialog extends StatelessWidget {
  final MemoriesProvider provider;

  const DesktopMemoryManagementDialog({
    super.key,
    required this.provider,
  });

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 420,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.98),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: Colors.white.withOpacity(0.08),
            width: 0.5,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.15),
              blurRadius: 40,
              offset: const Offset(0, 20),
              spreadRadius: -5,
            ),
            BoxShadow(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.05),
              blurRadius: 60,
              offset: const Offset(0, 0),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildHeader(context),
            _buildContent(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withOpacity(0.02),
            Colors.transparent,
          ],
        ),
        border: Border(
          bottom: BorderSide(
            color: Colors.white.withOpacity(0.05),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  ResponsiveHelper.purplePrimary.withOpacity(0.15),
                  ResponsiveHelper.purplePrimary.withOpacity(0.08),
                ],
              ),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                width: 0.5,
              ),
            ),
            child: const Icon(
              FontAwesomeIcons.sliders,
              color: ResponsiveHelper.purplePrimary,
              size: 16,
            ),
          ),
          const SizedBox(width: 16),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Memory Management',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    letterSpacing: -0.3,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Organize and control your memories',
                  style: TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ],
            ),
          ),
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => Navigator.pop(context),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.close,
                  color: ResponsiveHelper.textTertiary,
                  size: 16,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildMemoryStats(context),
          const SizedBox(height: 24),
          _buildManagementActions(context),
        ],
      ),
    );
  }

  Widget _buildMemoryStats(BuildContext context) {
    final totalMemories = provider.memories.length;
    final publicMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'public').length;
    final privateMemories = provider.memories.where((m) => !m.deleted && m.visibility.name == 'private').length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: _buildStatItem('Total', totalMemories.toString())),
            const SizedBox(width: 12),
            Expanded(child: _buildStatItem('Public', publicMemories.toString())),
            const SizedBox(width: 12),
            Expanded(child: _buildStatItem('Private', privateMemories.toString())),
          ],
        ),
      ],
    );
  }

  Widget _buildStatItem(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withOpacity(0.03),
            Colors.white.withOpacity(0.01),
          ],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withOpacity(0.06),
          width: 0.5,
        ),
      ),
      child: Column(
        children: [
          Text(
            value,
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 28,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w500,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildManagementActions(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Privacy actions
        _buildActionItem(
          'Make All Memories Private',
          'Set all memories to private visibility',
          () => _makeAllMemoriesPrivate(context),
        ),

        _buildActionItem(
          'Make All Memories Public',
          'Set all memories to public visibility',
          () => _makeAllMemoriesPublic(context),
        ),

        const SizedBox(height: 16),

        // Divider
        Container(
          height: 1,
          margin: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                Colors.transparent,
                Colors.white.withOpacity(0.06),
                Colors.transparent,
              ],
            ),
          ),
        ),

        const SizedBox(height: 16),

        // Danger zone
        _buildActionItem(
          'Delete All Memories',
          'Permanently remove all memories from Omi',
          () => _confirmDeleteAllMemories(context),
          isDangerous: true,
        ),
      ],
    );
  }

  Widget _buildActionItem(
    String title,
    String description,
    VoidCallback onPressed, {
    bool isDangerous = false,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Colors.white.withOpacity(0.02),
            Colors.transparent,
          ],
        ),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: isDangerous ? Colors.red.withOpacity(0.15) : Colors.white.withOpacity(0.04),
          width: 0.5,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(10),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: isDangerous ? Colors.red.shade400 : ResponsiveHelper.textPrimary,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          letterSpacing: -0.1,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        description,
                        style: TextStyle(
                          color: isDangerous ? Colors.red.shade300 : ResponsiveHelper.textSecondary,
                          fontSize: 12,
                          fontWeight: FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: isDangerous ? Colors.red.withOpacity(0.1) : Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(
                    FontAwesomeIcons.chevronRight,
                    size: 10,
                    color: isDangerous ? Colors.red.shade400 : ResponsiveHelper.textTertiary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _makeAllMemoriesPrivate(BuildContext context) async {
    Navigator.pop(context);
    await provider.updateAllMemoriesVisibility(true);

    if (context.mounted) {
      _showSuccessMessage(context, 'All memories are now private', FontAwesomeIcons.userLock);
    }
  }

  void _makeAllMemoriesPublic(BuildContext context) async {
    Navigator.pop(context);
    await provider.updateAllMemoriesVisibility(false);

    if (context.mounted) {
      _showSuccessMessage(context, 'All memories are now public', FontAwesomeIcons.userGroup);
    }
  }

  void _confirmDeleteAllMemories(BuildContext context) {
    if (provider.memories.isEmpty) {
      _showInfoMessage(context, 'No memories to delete');
      Navigator.pop(context);
      return;
    }

    showDialog(
      context: context,
      builder: (context) => Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          width: 400,
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.95),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.white.withOpacity(0.1),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 30,
                offset: const Offset(0, 15),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(50),
                  ),
                  child: Icon(
                    FontAwesomeIcons.triangleExclamation,
                    color: Colors.red.shade400,
                    size: 32,
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Clear Omi\'s Memory',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Are you sure you want to clear Omi\'s memory? This action cannot be undone and will permanently delete all ${provider.memories.length} memories.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () => Navigator.pop(context),
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Text(
                              'Cancel',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: ResponsiveHelper.textSecondary,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            provider.deleteAllMemories();
                            Navigator.pop(context); // Close confirmation dialog
                            Navigator.pop(context); // Close management dialog
                            _showSuccessMessage(
                                context, 'Omi\'s memory about you has been cleared', FontAwesomeIcons.trash);
                          },
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            decoration: BoxDecoration(
                              color: Colors.red.shade400,
                              borderRadius: BorderRadius.circular(12),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.red.shade400.withOpacity(0.3),
                                  blurRadius: 8,
                                  offset: const Offset(0, 2),
                                ),
                              ],
                            ),
                            child: const Text(
                              'Clear Memory',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showSuccessMessage(BuildContext context, String message, IconData icon) {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;
    entry = OverlayEntry(
      builder: (_) => Positioned(
        top: 50,
        right: 20,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: Colors.green.shade600,
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, color: Colors.white, size: 16),
                const SizedBox(width: 8),
                Text(
                  message,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    overlay.insert(entry);
    Future.delayed(const Duration(seconds: 3), () => entry.remove());
  }

  void _showInfoMessage(BuildContext context, String message) {
    final overlay = Overlay.of(context);
    late OverlayEntry entry;
    entry = OverlayEntry(
      builder: (_) => Positioned(
        top: 50,
        right: 20,
        child: Material(
          color: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary,
              borderRadius: BorderRadius.circular(12),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.2),
                  blurRadius: 8,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(FontAwesomeIcons.info, color: ResponsiveHelper.textSecondary, size: 16),
                const SizedBox(width: 8),
                Text(
                  message,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    overlay.insert(entry);
    Future.delayed(const Duration(seconds: 2), () => entry.remove());
  }
}
