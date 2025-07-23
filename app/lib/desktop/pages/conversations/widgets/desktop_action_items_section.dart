import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/ui/atoms/omi_checkbox.dart';
import 'package:omi/ui/molecules/omi_section_header.dart';

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
        OmiSectionHeader(
          icon: FontAwesomeIcons.listCheck,
          title: 'Action Items',
          badgeLabel: '${actionItems.length}',
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
                Container(
                  margin: const EdgeInsets.only(top: 2),
                  child: OmiCheckbox(
                    value: item.completed,
                    onChanged: (_) => _toggleCompletion(context, item, itemIndex),
                    size: 18,
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
          item.description,
          newValue,
        );
  }
}
