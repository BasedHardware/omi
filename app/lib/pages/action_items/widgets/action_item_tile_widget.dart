import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/action_items.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';

import 'action_item_form_sheet.dart';

class ActionItemTileWidget extends StatefulWidget {
  final ActionItemWithMetadata actionItem;
  final Function(bool) onToggle;
  final VoidCallback? onRefresh;
  final bool isSelectionMode;
  final bool isSelected;
  final VoidCallback? onLongPress;
  final VoidCallback? onSelectionToggle;
  final bool isSnoozedTab;

  const ActionItemTileWidget({
    super.key,
    required this.actionItem,
    required this.onToggle,
    this.onRefresh,
    this.isSelectionMode = false,
    this.isSelected = false,
    this.onLongPress,
    this.onSelectionToggle,
    this.isSnoozedTab = false,
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

    // Track action item checked/unchecked
    MixpanelManager().actionItemChecked(
      actionItemId: widget.actionItem.id,
      completed: newState,
      timestamp: DateTime.now(),
    );

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
        onRefresh: widget.onRefresh,
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
    String dueDateText;

    // For snoozed tab, always show actual date/time instead of relative labels
    if (widget.isSnoozedTab) {
      chipColor = Colors.grey.withOpacity(0.2);
      textColor = Colors.grey.shade400;
      dueDateText = _formatDueDate(dueDate, showFullDate: true);
    } else if (widget.actionItem.completed) {
      chipColor = Colors.grey.withOpacity(0.2);
      textColor = Colors.grey.shade500;
      dueDateText = _formatDueDate(dueDate);
    } else if (isOverdue) {
      chipColor = Colors.red.withOpacity(0.15);
      textColor = Colors.red.shade300;
      dueDateText = _formatDueDate(dueDate);
    } else if (isToday) {
      chipColor = Colors.yellow.withOpacity(0.15);
      textColor = Colors.yellow.shade300;
      dueDateText = 'Today';
    } else if (isTomorrow) {
      chipColor = Colors.blue.withOpacity(0.15);
      textColor = Colors.blue.shade300;
      dueDateText = 'Tomorrow';
    } else if (isThisWeek) {
      chipColor = Colors.green.withOpacity(0.15);
      textColor = Colors.green.shade300;
      dueDateText = _formatDueDate(dueDate);
    } else {
      chipColor = Colors.purple.withOpacity(0.15);
      textColor = Colors.purple.shade300;
      dueDateText = _formatDueDate(dueDate);
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: chipColor,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          FaIcon(
            FontAwesomeIcons.solidCalendar,
            size: 11,
            color: textColor,
          ),
          const SizedBox(width: 6),
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Text(
              dueDateText,
              style: TextStyle(
                color: textColor,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && date1.month == date2.month && date1.day == date2.day;
  }

  String _formatDueDate(DateTime date, {bool showFullDate = false}) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    if (showFullDate) {
      final now = DateTime.now();
      final hour = date.hour;
      final minute = date.minute;
      final hasTime = hour != 0 || minute != 0;

      String dateStr = '${months[date.month - 1]} ${date.day}';

      if (date.year != now.year) {
        dateStr += ', ${date.year}';
      }

      if (hasTime && !(hour == 23 && minute == 59)) {
        final period = hour >= 12 ? 'PM' : 'AM';
        final displayHour = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
        final displayMinute = minute.toString().padLeft(2, '0');
        dateStr += ', $displayHour:$displayMinute $period';
      }

      return dateStr;
    }

    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final targetDate = DateTime(date.year, date.month, date.day);
    final difference = targetDate.difference(today).inDays;
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
      return '${months[date.month - 1]} ${date.day}';
    }
  }

  Widget _buildTaskExportIcon(BuildContext context) {
    // If already exported, show the export platform logo
    // Otherwise, show the currently selected task app
    TaskIntegrationApp displayApp;
    bool isExported = widget.actionItem.exported;

    if (isExported && widget.actionItem.exportPlatform != null) {
      // Show the platform it was exported to
      displayApp = TaskIntegrationApp.values.firstWhere(
        (app) => app.key == widget.actionItem.exportPlatform,
        orElse: () => TaskIntegrationApp.appleReminders,
      );
    } else {
      // Show the currently selected app for export
      final provider = context.watch<TaskIntegrationProvider>();
      displayApp = provider.selectedApp;
    }

    return GestureDetector(
      onTap: isExported ? null : () => _handleTaskExport(context, displayApp),
      child: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(8),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            // Task app logo or icon
            displayApp.logoPath != null
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: Image.asset(
                      displayApp.logoPath!,
                      width: 24,
                      height: 24,
                      fit: BoxFit.contain,
                    ),
                  )
                : Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(6),
                      color: displayApp.iconColor.withOpacity(0.2),
                    ),
                    child: Icon(
                      displayApp.icon,
                      color: displayApp.iconColor,
                      size: 16,
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

  Future<void> _handleTaskExport(BuildContext context, TaskIntegrationApp taskApp) async {
    if (taskApp == TaskIntegrationApp.appleReminders) {
      await _handleAppleRemindersExport(context);
    } else if (taskApp == TaskIntegrationApp.todoist) {
      await _handleTodoistExport(context);
    } else if (taskApp == TaskIntegrationApp.asana) {
      await _handleAsanaExport(context);
    } else if (taskApp == TaskIntegrationApp.googleTasks) {
      await _handleGoogleTasksExport(context);
    } else if (taskApp == TaskIntegrationApp.clickup) {
      await _handleClickUpExport(context);
    } else {
      // Show coming soon message for other integrations
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.info, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Text('${taskApp.displayName} integration coming soon'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  Future<void> _handleTodoistExport(BuildContext context) async {
    HapticFeedback.mediumImpact();

    final service = TodoistService();

    // Check if already exported
    if (widget.actionItem.exported) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Text('Already exported to ${widget.actionItem.exportPlatform ?? "another platform"}'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 2),
          ),
        );
      }
      return;
    }

    // Check if authenticated
    if (!service.isAuthenticated) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.error, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Please authenticate with Todoist in Settings > Task Integrations'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 4),
          ),
        );
      }
      return;
    }

    // Show loading state
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
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
              SizedBox(width: 12),
              Text('Adding to Todoist...'),
            ],
          ),
          backgroundColor: Colors.blue,
          duration: Duration(seconds: 3),
        ),
      );
    }

    // Create task in Todoist
    final success = await service.createTask(
      content: widget.actionItem.description,
      description: 'From Omi',
      dueDate: widget.actionItem.dueAt,
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
              Text(success ? 'Added to Todoist' : 'Failed to add to Todoist'),
            ],
          ),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );

      // If successful, update the action item with export metadata
      if (success) {
        final exportTime = DateTime.now();
        await updateActionItem(
          widget.actionItem.id,
          exported: true,
          exportDate: exportTime,
          exportPlatform: 'todoist',
        );

        // Track action item export
        MixpanelManager().actionItemExported(
          actionItemId: widget.actionItem.id,
          appName: 'Todoist',
          timestamp: exportTime,
        );

        widget.onRefresh?.call();
      }
    }
  }

  Future<void> _handleAsanaExport(BuildContext context) async {
    HapticFeedback.mediumImpact();

    final service = AsanaService();

    // Check if already exported
    if (widget.actionItem.exported) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Text('Already exported to ${widget.actionItem.exportPlatform ?? "another platform"}'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 2),
          ),
        );
      }
      return;
    }

    // Check if authenticated
    if (!service.isAuthenticated) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.error, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Please authenticate with Asana in Settings > Task Integrations'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 4),
          ),
        );
      }
      return;
    }

    // Show loading state
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
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
              SizedBox(width: 12),
              Text('Adding to Asana...'),
            ],
          ),
          backgroundColor: Colors.blue,
          duration: Duration(seconds: 3),
        ),
      );
    }

    // Create task in Asana (workspace/project from settings, assignee is current user)
    final success = await service.createTask(
      name: widget.actionItem.description,
      notes: 'From Omi',
      dueDate: widget.actionItem.dueAt,
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
              Text(success ? 'Added to Asana' : 'Failed to add to Asana'),
            ],
          ),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );

      // If successful, update the action item with export metadata
      if (success) {
        final exportTime = DateTime.now();
        await updateActionItem(
          widget.actionItem.id,
          exported: true,
          exportDate: exportTime,
          exportPlatform: 'asana',
        );

        // Track action item export
        MixpanelManager().actionItemExported(
          actionItemId: widget.actionItem.id,
          appName: 'Asana',
          timestamp: exportTime,
        );

        widget.onRefresh?.call();
      }
    }
  }

  Future<void> _handleGoogleTasksExport(BuildContext context) async {
    HapticFeedback.mediumImpact();

    final service = GoogleTasksService();

    // Check if already exported
    if (widget.actionItem.exported) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Text('Already exported to ${widget.actionItem.exportPlatform ?? "another platform"}'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 2),
          ),
        );
      }
      return;
    }

    // Check if authenticated
    if (!service.isAuthenticated) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.error, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Please authenticate with Google Tasks in Settings > Task Integrations'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 4),
          ),
        );
      }
      return;
    }

    // Show loading state
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
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
              SizedBox(width: 12),
              Text('Adding to Google Tasks...'),
            ],
          ),
          backgroundColor: Colors.blue,
          duration: Duration(seconds: 3),
        ),
      );
    }

    // Create task in Google Tasks
    final success = await service.createTask(
      title: widget.actionItem.description,
      notes: 'From Omi',
      dueDate: widget.actionItem.dueAt,
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
              Text(success ? 'Added to Google Tasks' : 'Failed to add to Google Tasks'),
            ],
          ),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );

      // If successful, update the action item with export metadata
      if (success) {
        final exportTime = DateTime.now();
        await updateActionItem(
          widget.actionItem.id,
          exported: true,
          exportDate: exportTime,
          exportPlatform: 'google_tasks',
        );

        // Track action item export
        MixpanelManager().actionItemExported(
          actionItemId: widget.actionItem.id,
          appName: 'Google Tasks',
          timestamp: exportTime,
        );

        widget.onRefresh?.call();
      }
    }
  }

  Future<void> _handleClickUpExport(BuildContext context) async {
    HapticFeedback.mediumImpact();

    final service = ClickUpService();

    // Check if authenticated
    if (!service.isAuthenticated) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Row(
              children: [
                Icon(Icons.error, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Text('Please authenticate with ClickUp in Settings > Task Integrations'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 4),
          ),
        );
      }
      return;
    }

    // Show loading state
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
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
              SizedBox(width: 12),
              Text('Adding to ClickUp...'),
            ],
          ),
          backgroundColor: Colors.blue,
          duration: Duration(seconds: 3),
        ),
      );
    }

    // Create task in ClickUp
    final success = await service.createTask(
      name: widget.actionItem.description,
      description: 'From Omi',
      dueDate: widget.actionItem.dueAt,
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
              Text(success ? 'Added to ClickUp' : 'Failed to add to ClickUp'),
            ],
          ),
          backgroundColor: success ? Colors.green : Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );

      // If successful, update the action item with export metadata
      if (success) {
        final exportTime = DateTime.now();
        await updateActionItem(
          widget.actionItem.id,
          exported: true,
          exportDate: exportTime,
          exportPlatform: 'clickup',
        );

        // Track action item export
        MixpanelManager().actionItemExported(
          actionItemId: widget.actionItem.id,
          appName: 'ClickUp',
          timestamp: exportTime,
        );

        widget.onRefresh?.call();
      }
    }
  }

  Future<void> _handleAppleRemindersExport(BuildContext context) async {
    if (!PlatformService.isApple) return;

    HapticFeedback.mediumImpact();

    final service = AppleRemindersService();

    // Check if already exported
    if (widget.actionItem.exported) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Text('Already exported to ${widget.actionItem.exportPlatform ?? "another platform"}'),
              ],
            ),
            backgroundColor: Colors.orange,
            duration: const Duration(seconds: 2),
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
      dueDate: widget.actionItem.dueAt,
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

      // If successful, update the action item with export metadata
      if (success) {
        final exportTime = DateTime.now();
        await updateActionItem(
          widget.actionItem.id,
          exported: true,
          exportDate: exportTime,
          exportPlatform: 'apple_reminders',
        );

        // Track action item export
        MixpanelManager().actionItemExported(
          actionItemId: widget.actionItem.id,
          appName: 'Apple Reminders',
          timestamp: exportTime,
        );

        widget.onRefresh?.call();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: Colors.transparent,
          width: 0,
        ),
      ),
      clipBehavior: Clip.hardEdge,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: widget.isSelectionMode ? widget.onSelectionToggle : () => _showEditSheet(context),
        onLongPress: widget.onLongPress,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 12, 4, 12),
          child: Stack(
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Selection checkbox when in selection mode
                  if (widget.isSelectionMode)
                    GestureDetector(
                      onTap: widget.onSelectionToggle,
                      child: Container(
                        width: 24,
                        height: 24,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: widget.isSelected ? Colors.deepPurpleAccent : Colors.grey.shade600,
                            width: 2,
                          ),
                          color: widget.isSelected ? Colors.deepPurpleAccent : Colors.transparent,
                        ),
                        child: widget.isSelected
                            ? const Icon(
                                Icons.check,
                                color: Colors.white,
                                size: 16,
                              )
                            : null,
                      ),
                    )
                  // Completion checkbox when not in selection mode
                  else
                    GestureDetector(
                      onTap: _handleToggle,
                      child: Padding(
                        padding: const EdgeInsets.only(top: 5),
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
                            color: (widget.actionItem.completed || _isAnimating)
                                ? Colors.deepPurpleAccent
                                : Colors.transparent,
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
                    ),
                  const SizedBox(width: 16),
                  // Action item text and due date
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Stack(
                                children: [
                                  Text(
                                    widget.actionItem.description,
                                    style: TextStyle(
                                      color: (widget.actionItem.completed || _isAnimating)
                                          ? Colors.grey.shade400
                                          : Colors.white,
                                      fontSize: 15,
                                      fontWeight: FontWeight.w400,
                                      height: 1.5,
                                      decoration: (widget.actionItem.completed || _isAnimating)
                                          ? TextDecoration.lineThrough
                                          : null,
                                      decorationColor: Colors.grey.shade400,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        if (widget.actionItem.dueAt != null) ...[
                          const SizedBox(height: 6),
                          _buildDueDateChip(),
                        ],
                      ],
                    ),
                  ),
                  // Task export icon
                  const SizedBox(width: 12),
                  _buildTaskExportIcon(context),
                ],
              ),
              if (widget.actionItem.isLocked)
                Positioned.fill(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 2.0, sigmaY: 2.0),
                    child: GestureDetector(
                      onTap: () {
                        MixpanelManager().paywallOpened('Action Item');
                        routeToPage(context, const UsagePage(showUpgradeDialog: true));
                        return;
                      },
                      child: Container(
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.01),
                          borderRadius: const BorderRadius.all(Radius.circular(8)),
                        ),
                        child: const Text(
                          'Upgrade to unlimited',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
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
