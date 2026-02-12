import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:intl/intl.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class AcceptSharedTasksSheet extends StatefulWidget {
  final String token;
  final String senderName;
  final List<Map<String, dynamic>> tasks;
  final VoidCallback? onAccepted;

  const AcceptSharedTasksSheet({
    super.key,
    required this.token,
    required this.senderName,
    required this.tasks,
    this.onAccepted,
  });

  @override
  State<AcceptSharedTasksSheet> createState() => _AcceptSharedTasksSheetState();
}

class _AcceptSharedTasksSheetState extends State<AcceptSharedTasksSheet> {
  bool _isAccepting = false;

  Future<void> _acceptTasks() async {
    setState(() => _isAccepting = true);

    final result = await action_items_api.acceptSharedActionItems(widget.token);

    if (!mounted) return;

    if (result != null) {
      final count = result['count'] ?? 0;
      HapticFeedback.mediumImpact();
      Navigator.pop(context);
      AppSnackbar.showSnackbar('Added $count task${count == 1 ? '' : 's'} to your list');
      widget.onAccepted?.call();
    } else {
      setState(() => _isAccepting = false);
      AppSnackbar.showSnackbarError('Failed to accept tasks. You may have already accepted this share.');
    }
  }

  String _formatDueDate(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      return DateFormat.yMMMd().format(date);
    } catch (_) {
      return dateStr;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Handle bar
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(bottom: 20),
              decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
            ),

            // Header
            Text(
              '${widget.senderName} shared ${widget.tasks.length} task${widget.tasks.length == 1 ? '' : 's'}',
              style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            Text('Add to your task list?', style: TextStyle(color: Colors.grey.shade400, fontSize: 15)),
            const SizedBox(height: 20),

            // Task list
            Flexible(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: widget.tasks.length,
                itemBuilder: (context, index) {
                  final task = widget.tasks[index];
                  final description = task['description'] as String? ?? '';
                  final dueAt = task['due_at'] as String?;

                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.white.withOpacity(0.08)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          width: 20,
                          height: 20,
                          margin: const EdgeInsets.only(top: 2),
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.grey.shade600, width: 2),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(description, style: const TextStyle(color: Colors.white, fontSize: 15)),
                              if (dueAt != null) ...[
                                const SizedBox(height: 4),
                                Text(
                                  'Due ${_formatDueDate(dueAt)}',
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 20),

            // Accept button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _isAccepting ? null : _acceptTasks,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.deepPurple,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  disabledBackgroundColor: Colors.deepPurple.withOpacity(0.5),
                ),
                child: _isAccepting
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : Text(
                        'Add ${widget.tasks.length} task${widget.tasks.length == 1 ? '' : 's'} to my list',
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
