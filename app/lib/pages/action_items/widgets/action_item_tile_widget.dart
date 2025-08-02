import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/schema.dart';
import 'edit_action_item_sheet.dart';

class ActionItemTileWidget extends StatelessWidget {
  final ActionItemWithMetadata actionItem;
  final Function(bool) onToggle;

  const ActionItemTileWidget({
    super.key,
    required this.actionItem,
    required this.onToggle,
  });

  void _showEditSheet(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => EditActionItemBottomSheet(
        actionItem: actionItem,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: const Color(0xFF1F1F25),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: actionItem.completed 
            ? Colors.grey.withOpacity(0.2)
            : Colors.transparent,
          width: 1,
        ),
      ),
      clipBehavior: Clip.hardEdge,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _showEditSheet(context),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              // Custom checkbox with better styling
              GestureDetector(
                onTap: () => onToggle(!actionItem.completed),
                child: Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: actionItem.completed 
                        ? Colors.deepPurpleAccent 
                        : Colors.grey.shade600,
                      width: 2,
                    ),
                    color: actionItem.completed 
                      ? Colors.deepPurpleAccent 
                      : Colors.transparent,
                  ),
                  child: actionItem.completed
                    ? const Icon(
                        Icons.check,
                        color: Colors.white,
                        size: 16,
                      )
                    : null,
                ),
              ),
              const SizedBox(width: 16),
              // Action item text
              Expanded(
                child: Text(
                  actionItem.description,
                  style: TextStyle(
                    color: actionItem.completed ? Colors.grey.shade400 : Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w400,
                    decoration: actionItem.completed ? TextDecoration.lineThrough : null,
                    decorationColor: Colors.grey.shade400,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
} 