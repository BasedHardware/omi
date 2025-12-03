import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/chat_session_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

class ChatSessionsDrawer extends StatefulWidget {
  final String? currentAppId;
  final VoidCallback onSessionSelected;

  const ChatSessionsDrawer({
    super.key,
    required this.currentAppId,
    required this.onSessionSelected,
  });

  @override
  State<ChatSessionsDrawer> createState() => _ChatSessionsDrawerState();
}

class _ChatSessionsDrawerState extends State<ChatSessionsDrawer> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Force reload to get latest sessions (including newly created ones)
      context.read<ChatSessionProvider>().loadSessions(
            widget.currentAppId,
            forceReload: true,
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: const Color(0xFF1A1A1F),
      child: SafeArea(
        child: Column(
          children: [
            _buildHeader(context),
            const Divider(color: Colors.white12, height: 1),
            Expanded(
              child: Consumer<ChatSessionProvider>(
                builder: (context, provider, child) {
                  if (provider.isLoadingSessions) {
                    return const Center(
                      child: CircularProgressIndicator(
                        color: Colors.white54,
                      ),
                    );
                  }

                  if (provider.sessions.isEmpty) {
                    return const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.chat_bubble_outline,
                            size: 48,
                            color: Colors.white24,
                          ),
                          SizedBox(height: 16),
                          Text(
                            'No conversations yet',
                            style: TextStyle(
                              color: Colors.white54,
                              fontSize: 16,
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'Start a new chat!',
                            style: TextStyle(
                              color: Colors.white38,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  return ListView.builder(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: provider.sessions.length,
                    itemBuilder: (context, index) {
                      final session = provider.sessions[index];
                      final isSelected = session.id == provider.currentSessionId;
                      return _buildSessionTile(context, session, isSelected);
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 8, 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text(
            'Chat History',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add, color: Colors.white),
            onPressed: () => _createNewSession(context),
            tooltip: 'New Chat',
          ),
        ],
      ),
    );
  }

  Widget _buildSessionTile(BuildContext context, ChatSession session, bool isSelected) {
    // Get app name from AppProvider
    final appProvider = context.read<AppProvider>();
    String appLabel = 'Omi';
    if (!session.isOmiSession && session.effectiveAppId != null) {
      final app = appProvider.apps.where((a) => a.id == session.effectiveAppId).firstOrNull;
      appLabel = app?.name ?? 'App';
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: isSelected ? Colors.white.withOpacity(0.1) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: isSelected ? Colors.white.withOpacity(0.15) : Colors.white.withOpacity(0.08),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            Icons.chat_bubble_outline,
            color: isSelected ? Colors.white : Colors.white54,
            size: 20,
          ),
        ),
        title: Text(
          session.displayTitle,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.white70,
            fontSize: 15,
            fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Row(
          children: [
            // App badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              margin: const EdgeInsets.only(right: 6),
              decoration: BoxDecoration(
                color: session.isOmiSession ? Colors.blue.withOpacity(0.2) : Colors.purple.withOpacity(0.2),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                appLabel,
                style: TextStyle(
                  color: session.isOmiSession ? Colors.blue[300] : Colors.purple[300],
                  fontSize: 10,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            // Time ago
            Expanded(
              child: Text(
                session.timeAgo,
                style: const TextStyle(
                  color: Colors.white38,
                  fontSize: 12,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        trailing: PopupMenuButton<String>(
          icon: const Icon(
            Icons.more_vert,
            color: Colors.white38,
            size: 20,
          ),
          color: const Color(0xFF2A2A2F),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          onSelected: (value) => _handleSessionAction(context, value, session),
          itemBuilder: (context) => [
            const PopupMenuItem(
              value: 'rename',
              child: Row(
                children: [
                  Icon(Icons.edit, color: Colors.white70, size: 18),
                  SizedBox(width: 12),
                  Text('Rename', style: TextStyle(color: Colors.white70)),
                ],
              ),
            ),
            const PopupMenuItem(
              value: 'delete',
              child: Row(
                children: [
                  Icon(Icons.delete_outline, color: Colors.redAccent, size: 18),
                  SizedBox(width: 12),
                  Text('Delete', style: TextStyle(color: Colors.redAccent)),
                ],
              ),
            ),
          ],
        ),
        onTap: () => _selectSession(context, session),
      ),
    );
  }

  void _selectSession(BuildContext context, ChatSession session) {
    HapticFeedback.selectionClick();
    final sessionProvider = context.read<ChatSessionProvider>();
    final appProvider = context.read<AppProvider>();
    final messageProvider = context.read<MessageProvider>();

    if (sessionProvider.currentSessionId == session.id) {
      Navigator.pop(context); // Just close drawer
      return;
    }

    // Switch to session's app if different
    final sessionAppId = session.effectiveAppId;
    if (sessionAppId != appProvider.selectedChatAppId) {
      appProvider.setSelectedChatAppId(sessionAppId ?? 'no_selected');
    }

    sessionProvider.setCurrentSessionId(session.id);

    // Refresh messages for the new session
    messageProvider.refreshMessages(
      chatSessionId: session.id,
    );

    Navigator.pop(context); // Close drawer
    widget.onSessionSelected();
  }

  Future<void> _createNewSession(BuildContext context) async {
    HapticFeedback.mediumImpact();
    final provider = context.read<ChatSessionProvider>();
    final messageProvider = context.read<MessageProvider>();

    final newSession = await provider.createNewSession(widget.currentAppId);

    if (newSession != null && context.mounted) {
      // Clear current messages and load empty session
      messageProvider.refreshMessages(chatSessionId: newSession.id);
      Navigator.pop(context);
      widget.onSessionSelected();
    }
  }

  void _handleSessionAction(BuildContext context, String action, ChatSession session) {
    switch (action) {
      case 'rename':
        _showRenameDialog(context, session);
        break;
      case 'delete':
        _showDeleteConfirmation(context, session);
        break;
    }
  }

  void _showRenameDialog(BuildContext context, ChatSession session) {
    final controller = TextEditingController(text: session.title ?? 'New Chat');

    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: const Color(0xFF2A2A2F),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Text(
            'Rename Chat',
            style: TextStyle(color: Colors.white),
          ),
          content: TextField(
            controller: controller,
            autofocus: true,
            style: const TextStyle(color: Colors.white),
            decoration: InputDecoration(
              hintText: 'Enter new name',
              hintStyle: const TextStyle(color: Colors.white38),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white24),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: Colors.white54),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
            ),
            TextButton(
              onPressed: () async {
                final newTitle = controller.text.trim();
                if (newTitle.isNotEmpty) {
                  await context.read<ChatSessionProvider>().updateSessionTitle(
                        session.id,
                        newTitle,
                      );
                }
                if (ctx.mounted) Navigator.pop(ctx);
              },
              child: const Text('Save', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  void _showDeleteConfirmation(BuildContext context, ChatSession session) {
    showDialog(
      context: context,
      builder: (ctx) {
        return getDialog(
          context,
          () => Navigator.pop(ctx),
          () async {
            final provider = context.read<ChatSessionProvider>();
            final messageProvider = context.read<MessageProvider>();

            await provider.deleteSession(session.id);

            // If we deleted the current session, load the new current session's messages
            if (provider.currentSessionId != null) {
              messageProvider.refreshMessages(chatSessionId: provider.currentSessionId);
            } else {
              // No sessions left, clear messages
              messageProvider.refreshMessages();
            }

            if (ctx.mounted) Navigator.pop(ctx);
          },
          'Delete Chat?',
          'This will permanently delete this chat and all its messages.',
        );
      },
    );
  }
}
