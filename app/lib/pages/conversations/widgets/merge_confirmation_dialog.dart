import 'dart:io';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';

class MergeConfirmationDialog extends StatelessWidget {
  final int count;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  const MergeConfirmationDialog({
    super.key,
    required this.count,
    required this.onConfirm,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    if (Platform.isIOS) {
      return CupertinoAlertDialog(
        title: const Text('Merge Conversations'),
        content: Text(
          'This will combine $count conversations into one. '
          'All content will be merged and regenerated.',
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
      content: Text(
        'This will combine $count conversations into one. '
        'All content will be merged and regenerated.',
        style: const TextStyle(
          color: Color(0xFF8E8E93),
          fontSize: 15,
        ),
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

  static Future<bool> show(
    BuildContext context,
    List<ServerConversation> selectedConversations,
  ) async {
    if (selectedConversations.length < 2) return false;

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => MergeConfirmationDialog(
        count: selectedConversations.length,
        onConfirm: () => Navigator.of(context).pop(true),
        onCancel: () => Navigator.of(context).pop(false),
      ),
    );

    return result ?? false;
  }
}
