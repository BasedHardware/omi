import 'dart:io';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';

class MergeConfirmationDialog extends StatelessWidget {
  final int count;
  final String? warningMessage;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  const MergeConfirmationDialog({
    super.key,
    required this.count,
    this.warningMessage,
    required this.onConfirm,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final hasWarning = warningMessage != null && warningMessage!.isNotEmpty;

    if (Platform.isIOS) {
      return CupertinoAlertDialog(
        title: const Text('Merge Conversations'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'This will combine $count conversations into one. '
              'All content will be merged and regenerated.',
            ),
            if (hasWarning) ...[
              const SizedBox(height: 12),
              Text(
                '⚠️ $warningMessage',
                style: const TextStyle(
                  color: CupertinoColors.systemOrange,
                  fontSize: 13,
                ),
              ),
            ],
          ],
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: onCancel,
            child: const Text('Cancel'),
          ),
          CupertinoDialogAction(
            onPressed: onConfirm,
            isDefaultAction: true,
            child: const Text('Merge'),
          ),
        ],
      );
    }

    return AlertDialog(
      backgroundColor: const Color(0xFF1C1C1E),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
      ),
      title: const Text(
        'Merge Conversations',
        style: TextStyle(
          color: Colors.white,
          fontSize: 17,
          fontWeight: FontWeight.w600,
        ),
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'This will combine $count conversations into one. '
            'All content will be merged and regenerated.',
            style: const TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 15,
            ),
          ),
          if (hasWarning) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.orange.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(
                    Icons.warning_amber_rounded,
                    color: Colors.orange,
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      warningMessage!,
                      style: const TextStyle(
                        color: Colors.orange,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: onCancel,
          child: const Text(
            'Cancel',
            style: TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 17,
            ),
          ),
        ),
        TextButton(
          onPressed: onConfirm,
          child: const Text(
            'Merge',
            style: TextStyle(
              color: Color(0xFF7C3AED),
              fontSize: 17,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  /// Check for large time gaps between consecutive conversations
  static String? _checkForLargeGaps(List<ServerConversation> conversations) {
    if (conversations.length < 2) return null;

    // Sort by start time
    final sorted = List<ServerConversation>.from(conversations);
    sorted.sort((a, b) => (a.startedAt ?? a.createdAt).compareTo(b.startedAt ?? b.createdAt));

    final gaps = <String>[];
    for (int i = 1; i < sorted.length; i++) {
      final prevEnd = sorted[i - 1].finishedAt ?? sorted[i - 1].createdAt;
      final currStart = sorted[i].startedAt ?? sorted[i].createdAt;
      final gapHours = currStart.difference(prevEnd).inMinutes / 60.0;

      if (gapHours > 1) {
        gaps.add('${gapHours.toStringAsFixed(1)}h');
      }
    }

    if (gaps.isEmpty) return null;

    if (gaps.length == 1) {
      return 'Large time gap detected (${gaps.first})';
    }
    return 'Large time gaps detected (${gaps.join(", ")})';
  }

  static Future<bool> show(
    BuildContext context,
    List<ServerConversation> selectedConversations,
  ) async {
    if (selectedConversations.length < 2) return false;

    // Check for large gaps
    final warning = _checkForLargeGaps(selectedConversations);

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => MergeConfirmationDialog(
        count: selectedConversations.length,
        warningMessage: warning,
        onConfirm: () => Navigator.of(context).pop(true),
        onCancel: () => Navigator.of(context).pop(false),
      ),
    );

    return result ?? false;
  }
}
