import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class DesktopActionItemsSection extends StatelessWidget {
  final ServerConversation conversation;

  const DesktopActionItemsSection({
    super.key,
    required this.conversation,
  });

  @override
  Widget build(BuildContext context) {
    final actionItems = conversation.structured.actionItems.where((item) => !item.deleted).toList();

    if (actionItems.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section header
        Row(
          children: [
            const Icon(
              FontAwesomeIcons.listCheck,
              color: ResponsiveHelper.textSecondary,
              size: 16,
            ),
            const SizedBox(width: 8),
            const Text(
              'Action Items',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                '${actionItems.length}',
                style: const TextStyle(
                  color: ResponsiveHelper.textTertiary,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),

        const SizedBox(height: 16),

        // Action items list
        ...actionItems.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final itemIndex = conversation.structured.actionItems.indexOf(item);

          return Container(
            margin: EdgeInsets.only(bottom: index == actionItems.length - 1 ? 0 : 12),
            padding: const EdgeInsets.all(16),
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
                GestureDetector(
                  onTap: () => _toggleCompletion(context, item, itemIndex),
                  child: Container(
                    width: 18,
                    height: 18,
                    margin: const EdgeInsets.only(top: 2),
                    decoration: BoxDecoration(
                      color: item.completed ? ResponsiveHelper.purplePrimary : Colors.transparent,
                      border: Border.all(
                        color: item.completed ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                        width: 1.5,
                      ),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: item.completed
                        ? const Icon(
                            FontAwesomeIcons.check,
                            size: 10,
                            color: Colors.white,
                          )
                        : null,
                  ),
                ),

                const SizedBox(width: 12),

                // Content
                Expanded(
                  child: Text(
                    item.description,
                    style: TextStyle(
                      color: item.completed ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                      decoration: item.completed ? TextDecoration.lineThrough : null,
                      decorationColor: ResponsiveHelper.textTertiary,
                      fontSize: 15,
                      height: 1.4,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          );
        }),
      ],
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
}
