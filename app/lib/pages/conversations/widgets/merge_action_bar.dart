import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/pages/conversations/widgets/merge_confirmation_dialog.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';

class MergeActionBar extends StatefulWidget {
  const MergeActionBar({super.key});

  @override
  State<MergeActionBar> createState() => _MergeActionBarState();
}

class _MergeActionBarState extends State<MergeActionBar> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 300),
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 1),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, provider, child) {
        final isActive = provider.isSelectionModeActive;
        final count = provider.selectedConversationIds.length;
        final canMerge = provider.canMerge;

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
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.5),
                    blurRadius: 20,
                    offset: const Offset(0, -4),
                  ),
                ],
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                  child: Row(
                    children: [
                      // Cancel button
                      GestureDetector(
                        onTap: () {
                          HapticFeedback.lightImpact();
                          provider.exitSelectionMode();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                          child: Text(
                            context.l10n.cancel,
                            style: const TextStyle(
                              color: Color(0xFF8E8E93),
                              fontSize: 17,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ),

                      const Spacer(),

                      // Center: Selection count
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 150),
                        child: Text(
                          context.l10n.selectedCount(count),
                          key: ValueKey(count),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 17,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),

                      const Spacer(),

                      // Merge button
                      GestureDetector(
                        onTap: canMerge ? () => _handleMerge(context, provider) : null,
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 200),
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                          decoration: BoxDecoration(
                            color: canMerge ? const Color(0xFF7C3AED) : const Color(0xFF2C2C2E),
                            borderRadius: BorderRadius.circular(22),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.merge_rounded,
                                size: 18,
                                color: canMerge ? Colors.white : const Color(0xFF636366),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                context.l10n.merge,
                                style: TextStyle(
                                  color: canMerge ? Colors.white : const Color(0xFF636366),
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
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

  Future<void> _handleMerge(BuildContext context, ConversationProvider provider) async {
    HapticFeedback.mediumImpact();
    final confirmed = await MergeConfirmationDialog.show(
      context,
      provider.selectedConversations,
    );
    if (confirmed && context.mounted) {
      final idsToMerge = provider.markSelectedAsMergingAndExit();

      final response = await provider.initiateConversationMerge(conversationIds: idsToMerge);

      if (context.mounted) {
        if (response != null) {
          // Show a simple, non-blocking message
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                context.l10n.mergingInBackground,
              ),
              backgroundColor: const Color(0xFF2C2C2E),
              behavior: SnackBarBehavior.floating,
              margin: const EdgeInsets.all(16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
              duration: const Duration(seconds: 3),
              action: SnackBarAction(
                label: 'OK',
                textColor: Colors.white70,
                onPressed: () {},
              ),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.failedToStartMerge),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              margin: const EdgeInsets.all(16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
        }
      }
    }
  }
}
