import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/providers/chat_session_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/molecules/omi_session_tile.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class MobileSessionsHistoryPage extends StatefulWidget {
  const MobileSessionsHistoryPage({super.key});

  @override
  State<MobileSessionsHistoryPage> createState() => _MobileSessionsHistoryPageState();
}

class _MobileSessionsHistoryPageState extends State<MobileSessionsHistoryPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Ensure sessions are loaded
      context.read<ChatSessionProvider>().loadSessions();
    });
  }

  void _handleSessionTap(ChatSession session) async {
    final sessionProvider = context.read<ChatSessionProvider>();
    final messageProvider = context.read<MessageProvider>();
    
    // Switch to the selected session
    sessionProvider.switchToSession(session);
    
    // Refresh messages for the selected session
    messageProvider.refreshMessages(chatSessionId: session.id);
    
    // Navigate back to chat
    if (mounted) {
      Navigator.of(context).pop();
    }
  }

  void _handleDeleteSession(ChatSession session) async {
    final result = await OmiConfirmDialog.show(
      context,
      title: 'Delete Session?',
      message: 'Are you sure you want to delete the chat session "${session.displayTitle}"? This action cannot be undone.',
      confirmLabel: 'Delete',
    );

    if (result == true && mounted) {
      final sessionProvider = context.read<ChatSessionProvider>();
      await sessionProvider.deleteSession(session);
      
      // Refresh messages for the new current session
      final messageProvider = context.read<MessageProvider>();
      await messageProvider.refreshMessages(chatSessionId: sessionProvider.currentSessionId);
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Chat session "${session.displayTitle}" deleted'),
            backgroundColor: Theme.of(context).colorScheme.secondary,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  void _handleCreateNewSession() async {
    final sessionProvider = context.read<ChatSessionProvider>();
    final messageProvider = context.read<MessageProvider>();

    Navigator.of(context).pop();
    
    await sessionProvider.createNewSession();
    
    // Refresh messages for the new session
    await messageProvider.refreshMessages(chatSessionId: sessionProvider.currentSessionId);
    
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<ChatSessionProvider, AppProvider, MessageProvider>(
      builder: (context, sessionProvider, appProvider, messageProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.surface,
            elevation: 0,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
              onPressed: () => Navigator.of(context).pop(),
            ),
            title: const Text(
              'Chat Sessions',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            centerTitle: true,
            actions: [
              IconButton(
                icon: const Icon(FontAwesomeIcons.plus, color: Colors.white, size: 18),
                onPressed: _handleCreateNewSession,
                tooltip: 'New Session',
              ),
            ],
          ),
          body: sessionProvider.isLoadingSessions
              ? const Center(
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              : sessionProvider.sessions.isEmpty
                  ? _buildEmptyState()
                  : _buildSessionsList(sessionProvider),
        );
      },
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            FontAwesomeIcons.comments,
            size: 64,
            color: Colors.grey.shade600,
          ),
          const SizedBox(height: 16),
          Text(
            'No chat sessions yet',
            style: TextStyle(
              color: Colors.grey.shade300,
              fontSize: 18,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Start a new conversation to create your first session',
            style: TextStyle(
              color: Colors.grey.shade500,
              fontSize: 14,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _handleCreateNewSession,
            icon: const Icon(FontAwesomeIcons.plus, size: 16),
            label: const Text('Start New Chat'),
            style: ElevatedButton.styleFrom(
              backgroundColor: ResponsiveHelper.purplePrimary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSessionsList(ChatSessionProvider sessionProvider) {
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: sessionProvider.sessions.length,
      separatorBuilder: (context, index) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final session = sessionProvider.sessions[index];
        final isActive = session.id == sessionProvider.currentSessionId;
        
        return OmiSessionTile(
          title: session.displayTitle,
          subtitle: _formatSessionTime(session.createdAt),
          isActive: isActive,
          onTap: () => _handleSessionTap(session),
          onDelete: sessionProvider.sessions.length > 1 
              ? () => _handleDeleteSession(session) 
              : null,
          showDeleteButton: sessionProvider.sessions.length > 1,
        );
      },
    );
  }

  String _formatSessionTime(DateTime createdAt) {
    final now = DateTime.now();
    final difference = now.difference(createdAt);
    
    if (difference.inMinutes < 1) {
      return 'Just now';
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes}m ago';
    } else if (difference.inHours < 24) {
      return '${difference.inHours}h ago';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}d ago';
    } else {
      return '${createdAt.day}/${createdAt.month}/${createdAt.year}';
    }
  }
} 