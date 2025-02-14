import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/chat_session.dart';

class ChatHistoryItem extends StatelessWidget {
  final ChatSession session;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  final Function(String) onRename;

  const ChatHistoryItem({
    super.key,
    required this.session,
    required this.onTap,
    required this.onDelete,
    required this.onRename,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
  onTap: onTap,
  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
  title: Row(
    crossAxisAlignment: CrossAxisAlignment.center,
    children: [
      Expanded(
        child: Text(
          session.name,
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w500,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      const SizedBox(width: 8),
      // Edit button
      Container(
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(8),
        ),
        child: InkWell(
          onTap: () => _showRenameDialog(context),
          borderRadius: BorderRadius.circular(8),
          child: const Padding(
            padding: EdgeInsets.all(8.0),
            child: Icon(
              Icons.edit_outlined,
              size: 20,
              color: Colors.white70,
            ),
          ),
        ),
      ),
      const SizedBox(width: 8),
      // Delete button
      Container(
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(8),
        ),
        child: InkWell(
          onTap: () => _showDeleteConfirmation(context),
          borderRadius: BorderRadius.circular(8),
          child: const Padding(
            padding: EdgeInsets.all(8.0),
            child: Icon(
              Icons.delete_outline,
              size: 20,
              color: Colors.red,
            ),
          ),
        ),
      ),
    ],
  ),
  subtitle: Text(
    _formatDate(session.lastMessageDate),
    style: TextStyle(color: Colors.grey[400]),
  ),
  trailing: const Icon(
    Icons.arrow_forward_ios,
    color: Colors.white60,
    size: 16,
  ),
);
  }

  Future<void> _showDeleteConfirmation(BuildContext context) async {
    return showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: Theme.of(context).colorScheme.onPrimaryContainer,
          title: const Text(
            'Delete Chat',
            style: TextStyle(color: Colors.white),
          ),
          content: const Text(
            'Are you sure you want to delete this chat? This action cannot be undone.',
            style: TextStyle(color: Colors.white70),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text(
                'Cancel',
                style: TextStyle(color: Colors.white70),
              ),
            ),
            TextButton(
              onPressed: () {
                Navigator.of(context).pop();
                onDelete();
              },
              style: TextButton.styleFrom(
                foregroundColor: Colors.red,
              ),
              child: const Text('Delete'),
            ),
          ],
        );
      },
    );
  }

  void _showRenameDialog(BuildContext context) {
      final controller = TextEditingController(text: session.name);
      final focusNode = FocusNode();

      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (context) => Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          child: Container(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surface,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(20),
              ),
            ),
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  height: 4,
                  width: 40,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Container(
                  decoration: BoxDecoration(
                    color: Colors.black45,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: Colors.white24,
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: controller,
                          focusNode: focusNode,
                          autofocus: true,
                          style: const TextStyle(color: Colors.white),
                          decoration: const InputDecoration(
                            hintText: 'Enter chat name',
                            hintStyle: TextStyle(color: Colors.white38),
                            contentPadding: EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 14,
                            ),
                            border: InputBorder.none,
                          ),
                          onSubmitted: (value) {
                            if (value.isNotEmpty) {
                              onRename(value);
                              Navigator.pop(context);
                            }
                          },
                        ),
                      ),
                      TextButton(
                        onPressed: () {
                          final newName = controller.text.trim();
                          if (newName.isNotEmpty) {
                            onRename(newName);
                            Navigator.pop(context);
                          }
                        },
                        style: TextButton.styleFrom(
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                        ),
                        child: const Text('Save'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      // Focus the text field after the bottom sheet is shown
      Future.delayed(const Duration(milliseconds: 100), () {
        focusNode.requestFocus();
      });
    }

  String _formatDate(DateTime date) {
    return '${date.day}/${date.month}/${date.year} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
  }
}