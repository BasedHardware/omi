import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/conversation_actions.dart';
import 'package:omi/pages/conversations/widgets/merge_confirmation_dialog.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 300));
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
                color: OmiColors.surface1,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(OmiRadius.lg)),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 20, offset: const Offset(0, -4)),
                ],
              ),
              child: SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, OmiSpacing.md, OmiSpacing.md, OmiSpacing.md),
                  child: Row(
                    children: [
                      OmiButton.tertiary(
                        label: context.l10n.cancel,
                        size: OmiButtonSize.compact,
                        onPressed: () {
                          HapticFeedback.lightImpact();
                          provider.exitSelectionMode();
                        },
                      ),
                      Expanded(
                        child: AnimatedSwitcher(
                          duration: const Duration(milliseconds: 150),
                          child: Text(
                            context.l10n.selectedCount(count),
                            key: ValueKey(count),
                            textAlign: TextAlign.center,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.headline,
                          ),
                        ),
                      ),
                      // Bulk actions (hub audit #7): move and delete work on any selection; merge needs two.
                      OmiIconButton(
                        key: const Key('selection_bar_move'),
                        icon: const Icon(Icons.folder_outlined),
                        label: context.l10n.moveToFolder,
                        onPressed: count > 0 ? () => moveSelectedConversationsToFolder(context) : null,
                      ),
                      OmiIconButton(
                        key: const Key('selection_bar_delete'),
                        icon: const Icon(Icons.delete_outline_rounded),
                        label: context.l10n.delete,
                        isDestructive: true,
                        onPressed: count > 0 ? () => confirmAndDeleteSelectedConversations(context) : null,
                      ),
                      const SizedBox(width: OmiSpacing.xxs),
                      OmiButton(
                        key: const Key('selection_bar_merge'),
                        label: context.l10n.merge,
                        icon: Icons.merge_rounded,
                        size: OmiButtonSize.compact,
                        onPressed: canMerge ? () => _handleMerge(context, provider) : null,
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
    final confirmed = await MergeConfirmationDialog.show(context, provider.selectedConversations);
    if (confirmed && context.mounted) {
      final idsToMerge = provider.markSelectedAsMergingAndExit();

      final response = await provider.initiateConversationMerge(conversationIds: idsToMerge);

      if (context.mounted) {
        if (response != null) {
          OmiFeedback.info(context, context.l10n.mergingInBackground);
        } else {
          OmiFeedback.error(context, context.l10n.failedToStartMerge);
        }
      }
    }
  }
}
