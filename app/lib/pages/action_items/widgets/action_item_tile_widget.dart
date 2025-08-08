import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'edit_action_item_sheet.dart';

class ActionItemTileWidget extends StatelessWidget {
  final ActionItemWithMetadata actionItem;
  final Function(bool) onToggle;
  final Set<String>? exportedToAppleReminders;
  final VoidCallback? onExportedToAppleReminders;

  const ActionItemTileWidget({
    super.key,
    required this.actionItem,
    required this.onToggle,
    this.exportedToAppleReminders,
    this.onExportedToAppleReminders,
  });

  void _showEditSheet(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => EditActionItemBottomSheet(
        actionItem: actionItem,
        exportedToAppleReminders: exportedToAppleReminders,
        onExportedToAppleReminders: onExportedToAppleReminders,
      ),
    );
  }

  Widget _buildAppleRemindersIcon(BuildContext context) {
    final isExported = exportedToAppleReminders?.contains(actionItem.description) ?? false;
    
    return GestureDetector(
      onTap: () => _handleAppleRemindersExport(context),
      child: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            // Apple Reminders logo
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(6),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Image.asset(
                  Assets.images.appleRemindersLogo.path,
                  width: 24,
                  height: 24,
                  fit: BoxFit.contain,
                ),
              ),
            ),
            // Status indicator at bottom right
            Positioned(
              bottom: 0,
              right: 0,
              child: Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: isExported ? Colors.green : Colors.blue,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: const Color(0xFF1F1F25),
                    width: 1.5,
                  ),
                ),
                child: Icon(
                  isExported ? Icons.check : Icons.add,
                  color: Colors.white,
                  size: 8,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleAppleRemindersExport(BuildContext context) async {
    if (!PlatformService.isApple) return;

    HapticFeedback.mediumImpact();

    final service = AppleRemindersService();
    final isAlreadyExported = exportedToAppleReminders?.contains(actionItem.description) ?? false;
    
    if (isAlreadyExported) {
      // Show message that it's already exported
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.check_circle, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Already added to Apple Reminders'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 2),
          ),
        );
      }
      return;
    }

    // Check permissions and request if needed
    bool hasPermission = await service.hasPermission();
    
    if (!hasPermission) {
      // Request permission directly
      hasPermission = await service.requestPermission();
      
      if (!hasPermission) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Row(
                children: [
                  Icon(Icons.error, color: Colors.white, size: 20),
                  const SizedBox(width: 8),
                  Text('Permission denied for Apple Reminders'),
                ],
              ),
              backgroundColor: Colors.red,
              duration: const Duration(seconds: 3),
            ),
          );
        }
        return;
      }
    }

    // Show loading state
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              ),
              const SizedBox(width: 12),
              Text('Adding to Apple Reminders...'),
            ],
          ),
          backgroundColor: Colors.blue,
          duration: const Duration(seconds: 3),
        ),
      );
    }

    // Add to Apple Reminders
    final success = await service.addReminder(
      title: actionItem.description,
      notes: 'From Omi',
      listName: 'Reminders',
    );
    
    if (context.mounted) {
      // Clear the loading snackbar
      ScaffoldMessenger.of(context).clearSnackBars();
      
      // Show result
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                success ? Icons.check_circle : Icons.error, 
                color: Colors.white, 
                size: 20
              ),
              const SizedBox(width: 8),
              Text(success ? 'Added to Apple Reminders' : 'Failed to add to Reminders'),
            ],
          ),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );

      // If successful, update the exported list
      if (success) {
        onExportedToAppleReminders?.call();
      }
    }
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
              // Apple Reminders icon (only show on Apple platforms)
              if (PlatformService.isApple) ...[
                const SizedBox(width: 12),
                _buildAppleRemindersIcon(context),
              ],
            ],
          ),
        ),
      ),
    );
  }
} 