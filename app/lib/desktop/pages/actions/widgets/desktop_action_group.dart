import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/atoms/omi_icon_badge.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';


class DesktopActionGroup extends StatelessWidget {
  final ServerConversation conversation;
  final List<ActionItem> actionItems;

  const DesktopActionGroup({
    super.key,
    required this.conversation,
    required this.actionItems,
  });

  @override
  Widget build(BuildContext context) {
    final sortedItems = [...actionItems]..sort((a, b) {
        if (a.completed == b.completed) return 0;
        return a.completed ? 1 : -1;
      });

    final incompleteCount = sortedItems.where((item) => !item.completed).length;

    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 16),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Group header
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _navigateToConversationDetail(context),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
              ),
              child: Container(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    // Conversation icon
                    OmiIconBadge(
                      icon: FontAwesomeIcons.message,
                      bgColor: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                      iconColor: ResponsiveHelper.purplePrimary,
                      radius: 8,
                    ),

                    const SizedBox(width: 12),

                    // Conversation details
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            conversation.structured.title.isNotEmpty ? conversation.structured.title : 'Untitled Conversation',
                            style: const TextStyle(
                              color: ResponsiveHelper.textPrimary,
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '$incompleteCount remaining',
                            style: const TextStyle(
                              color: ResponsiveHelper.textSecondary,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),

                    // Navigate icon
                    const Icon(
                      FontAwesomeIcons.chevronRight,
                      color: ResponsiveHelper.textTertiary,
                      size: 12,
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Divider
          Container(
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: 16),
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          ),

          // Action items list
          ...sortedItems.asMap().entries.map((entry) {
            final index = entry.key;
            final item = entry.value;

            return Container(
              margin: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 12,
                bottom: index == sortedItems.length - 1 ? 16 : 0,
              ),
              child: _buildGroupedActionItem(context, item),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildGroupedActionItem(BuildContext context, ActionItem item) {
    final itemIndex = conversation.structured.actionItems.indexOf(item);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Checkbox
          OmiCheckbox(
            value: item.completed,
            onChanged: (v) => _toggleCompletion(context, item, itemIndex),
          ),

          const SizedBox(width: 10),

          // Content
          Expanded(
            child: Text(
              item.description,
              style: TextStyle(
                color: item.completed ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                decoration: item.completed ? TextDecoration.lineThrough : null,
                decorationColor: ResponsiveHelper.textTertiary,
                fontSize: 14,
                height: 1.3,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Quick action button
          OmiIconButton(
            icon: FontAwesomeIcons.pen,
            onPressed: () => _showEditActionSheet(context, item, itemIndex),
            style: OmiIconButtonStyle.outline,
            size: 24,
            color: ResponsiveHelper.textSecondary,
          ),
        ],
      ),
    );
  }

  void _toggleCompletion(BuildContext context, ActionItem item, int itemIndex) {
    final newValue = !item.completed;
    context.read<ConversationProvider>().updateGlobalActionItemState(
          conversation,
          itemIndex,
          newValue,
        );
  }

  void _showEditActionSheet(BuildContext context, ActionItem item, int itemIndex) {
    // For now, just show a simple snackbar - we'll implement the edit sheet later
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Edit functionality coming soon'),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _navigateToConversationDetail(BuildContext context) async {
    final convoProvider = Provider.of<ConversationProvider>(context, listen: false);

    DateTime? date;
    int? index;

    for (final entry in convoProvider.groupedConversations.entries) {
      final foundIndex = entry.value.indexWhere((c) => c.id == conversation.id);
      if (foundIndex != -1) {
        date = entry.key;
        index = foundIndex;
        break;
      }
    }

    if (date != null && index != null) {
      final detailProvider = Provider.of<ConversationDetailProvider>(context, listen: false);
      detailProvider.updateConversation(index, date);

      convoProvider.onConversationTap(index);

      await routeToPage(
        context,
        ConversationDetailPage(conversation: conversation),
      );
    }
  }
}
