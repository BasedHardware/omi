import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Bottom-anchored selection action bar for the action items page.
/// Same visual language as `MergeActionBar` for the conversations page —
/// dark sheet with rounded top corners, slide-up animation, single primary
/// pill action.
///
/// Mounted at the home page's outer Stack so it paints above the bottom
/// nav bar (mirrors `MergeActionBar`). Selection state lives in
/// `ActionItemsProvider`. Bulk-delete is intentionally not part of the bar:
/// per-row swipe-left handles individual delete, and the section header's
/// clear-completed path covers bulk-delete of completed tasks.
class TaskSelectionActionBar extends StatefulWidget {
  const TaskSelectionActionBar({super.key});

  @override
  State<TaskSelectionActionBar> createState() => _TaskSelectionActionBarState();
}

class _TaskSelectionActionBarState extends State<TaskSelectionActionBar> with SingleTickerProviderStateMixin {
  late final AnimationController _animationController;
  late final Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 280));
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animationController, curve: Curves.easeOutCubic));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        final isActive = provider.isSelectionMode;
        final taskCount = provider.selectedCount;
        final canExport = taskCount > 0;

        if (isActive) {
          _animationController.forward();
        } else {
          _animationController.reverse();
        }

        return IgnorePointer(
          ignoring: !isActive,
          child: SlideTransition(
            position: _slideAnimation,
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1C),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 20, offset: const Offset(0, -4)),
                ],
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                  child: Row(
                    children: [
                      // Cancel
                      GestureDetector(
                        onTap: () {
                          HapticFeedback.lightImpact();
                          provider.endSelection();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                          child: Text(
                            context.l10n.cancel,
                            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 17, fontWeight: FontWeight.w500),
                          ),
                        ),
                      ),
                      const Spacer(),
                      // Center: count
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 150),
                        child: Text(
                          context.l10n.selectedCount(taskCount, taskCount),
                          key: ValueKey(taskCount),
                          style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
                        ),
                      ),
                      const Spacer(),
                      // Export pill — single primary action. Bulk-delete is
                      // handled per-row via swipe-left and via the Clear-completed
                      // path in the section header — keeping the bar at one
                      // primary action mirrors the conversations merge bar.
                      _ActionPillButton(
                        icon: Icons.ios_share_rounded,
                        label: context.l10n.exportButton,
                        enabled: canExport,
                        accent: const Color(0xFF7C3AED),
                        onTap: () => _handleExport(context, provider),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _handleExport(BuildContext context, ActionItemsProvider provider) async {
    HapticFeedback.lightImpact();

    // Users connect one task app at a time. If none connected, nudge to
    // Settings; otherwise export directly to the connected app.
    final integrations = Provider.of<TaskIntegrationProvider>(context, listen: false);
    final connected = TaskIntegrationApp.values.where(integrations.isAppConnected).toList(growable: false);

    if (connected.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.connectTaskAppToExport),
          backgroundColor: const Color(0xFF2C2C2E),
          duration: const Duration(seconds: 4),
          action: SnackBarAction(
            label: context.l10n.connectAction,
            textColor: Colors.white,
            onPressed: () {
              Navigator.of(context).push(MaterialPageRoute(builder: (_) => const TaskIntegrationsPage()));
            },
          ),
        ),
      );
      return;
    }

    await provider.bulkExportSelected(context, connected.first);
  }
}

class _ActionPillButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool enabled;
  final Color accent;
  final VoidCallback onTap;

  const _ActionPillButton({
    required this.icon,
    required this.label,
    required this.enabled,
    required this.accent,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: enabled ? accent : const Color(0xFF2C2C2E),
          borderRadius: BorderRadius.circular(22),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 18, color: enabled ? Colors.white : const Color(0xFF636366)),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                color: enabled ? Colors.white : const Color(0xFF636366),
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
