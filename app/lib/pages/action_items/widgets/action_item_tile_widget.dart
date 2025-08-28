import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'action_item_form_sheet.dart';

class ActionItemTileWidget extends StatefulWidget {
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

  @override
  State<ActionItemTileWidget> createState() => _ActionItemTileWidgetState();
}

class _ActionItemTileWidgetState extends State<ActionItemTileWidget> {
  bool _isAnimating = false;

  @override
  void dispose() {
    super.dispose();
  }

  void _handleToggle() async {
    if (_isAnimating) return;

    HapticFeedback.mediumImpact();

    final newState = !widget.actionItem.completed;

    if (newState) {
      setState(() {
        _isAnimating = true;
      });

      await Future.delayed(const Duration(milliseconds: 500));

      widget.onToggle(newState);

      setState(() {
        _isAnimating = false;
      });
    } else {
      widget.onToggle(newState);
    }
  }

  void _showEditSheet(BuildContext context) {
    HapticFeedback.mediumImpact();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ActionItemFormSheet(
        actionItem: widget.actionItem,
        exportedToAppleReminders: widget.exportedToAppleReminders,
        onExportedToAppleReminders: widget.onExportedToAppleReminders,
      ),
    );
  }

  Widget _buildDueDateChip() {
    if (widget.actionItem.dueAt == null) return const SizedBox.shrink();

    final now = DateTime.now();
    final dueDate = widget.actionItem.dueAt!;
    final isOverdue = dueDate.isBefore(now) && !widget.actionItem.completed;
    final isToday = _isSameDay(dueDate, now);
    final isTomorrow = _isSameDay(dueDate, now.add(const Duration(days: 1)));
    final isThisWeek = dueDate.isAfter(now) && dueDate.isBefore(now.add(const Duration(days: 7)));

    Color chipColor;
    Color textColor;
    IconData icon;
    String dueDateText;

    if (widget.actionItem.completed) {
      chipColor = Colors.grey.withOpacity(0.2);
      textColor = Colors.grey.shade500;
      icon = Icons.check_circle_outline;
      dueDateText = _formatDueDate(dueDate);
    } else if (isOverdue) {
      chipColor = Colors.red.withOpacity(0.15);
      textColor = Colors.red.shade300;
      icon = Icons.warning_amber_rounded;
      dueDateText = 'Overdue';
    } else if (isToday) {
      chipColor = Colors.orange.withOpacity(0.15);
      textColor = Colors.orange.shade300;
      icon = Icons.today;
      dueDateText = 'Today';
    } else if (isTomorrow) {
      chipColor = Colors.blue.withOpacity(0.15);
      textColor = Colors.blue.shade300;
      icon = Icons.event;
      dueDateText = 'Tomorrow';
    } else if (isThisWeek) {
      chipColor = Colors.green.withOpacity(0.15);
      textColor = Colors.green.shade300;
      icon = Icons.calendar_today;
      dueDateText = _formatDueDate(dueDate);
    } else {
      chipColor = Colors.purple.withOpacity(0.15);
      textColor = Colors.purple.shade300;
      icon = Icons.schedule;
      dueDateText = _formatDueDate(dueDate);
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: chipColor,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 14,
            color: textColor,
          ),
          const SizedBox(width: 4),
          Text(
            dueDateText,
            style: TextStyle(
              color: textColor,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && date1.month == date2.month && date1.day == date2.day;
  }

  String _formatDueDate(DateTime date) {
    final now = DateTime.now();
    final difference = date.difference(now).inDays;

    if (difference == 0) {
      return 'Today';
    } else if (difference == 1) {
      return 'Tomorrow';
    } else if (difference == -1) {
      return 'Yesterday';
    } else if (difference > 1 && difference <= 7) {
      final weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return weekdays[date.weekday - 1];
    } else {
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      return '${months[date.month - 1]} ${date.day}';
    }
  }

  Widget _buildAppleRemindersIcon(BuildContext context) {
    final isExported = widget.exportedToAppleReminders?.contains(widget.actionItem.description) ?? false;

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
    final isAlreadyExported = widget.exportedToAppleReminders?.contains(widget.actionItem.description) ?? false;

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
      title: widget.actionItem.description,
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
              Icon(success ? Icons.check_circle : Icons.error, color: Colors.white, size: 20),
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
        widget.onExportedToAppleReminders?.call();
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
          color: widget.actionItem.completed ? Colors.grey.withOpacity(0.2) : Colors.transparent,
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
                onTap: _handleToggle,
                child: Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: (widget.actionItem.completed || _isAnimating)
                          ? Colors.deepPurpleAccent
                          : Colors.grey.shade600,
                      width: 2,
                    ),
                    color: (widget.actionItem.completed || _isAnimating) ? Colors.deepPurpleAccent : Colors.transparent,
                  ),
                  child: (widget.actionItem.completed || _isAnimating)
                      ? const Icon(
                          Icons.check,
                          color: Colors.white,
                          size: 16,
                        )
                      : null,
                ),
              ),
              const SizedBox(width: 16),
              // Action item text and due date
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.actionItem.description,
                      style: TextStyle(
                        color: (widget.actionItem.completed || _isAnimating) ? Colors.grey.shade400 : Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w400,
                        decoration: (widget.actionItem.completed || _isAnimating) ? TextDecoration.lineThrough : null,
                        decorationColor: Colors.grey.shade400,
                      ),
                    ),
                    if (widget.actionItem.dueAt != null) ...[
                      const SizedBox(height: 6),
                      _buildDueDateChip(),
                    ],
                  ],
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