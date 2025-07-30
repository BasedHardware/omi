import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/providers/chat_session_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
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

  Color _getSessionColor(int index) {
    final colors = [
      Colors.blue,
      Colors.green,
      Colors.orange,
      Colors.purple,
      Colors.red,
      Colors.teal,
      Colors.indigo,
      Colors.pink,
    ];
    return colors[index % colors.length];
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<ChatSessionProvider, AppProvider, MessageProvider>(
      builder: (context, sessionProvider, appProvider, messageProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          body: Column(
            children: [
              // Search bar and header
              Container(
                padding: EdgeInsets.only(
                  top: MediaQuery.of(context).padding.top + 16,
                  left: 12,
                  right: 12,
                  bottom: 6,
                ),
                child: Row(
                  children: [
                    // Back button
                    GestureDetector(
                      onTap: () => Navigator.of(context).pop(),
                      child: Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: const Color(0xFF151415),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Center(
                          child: Icon(
                            Icons.arrow_back_ios,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: TextField(
                          enabled: false,
                          style: const TextStyle(color: Colors.white),
                          decoration: InputDecoration(
                            hintText: 'Search chats...',
                            hintStyle: TextStyle(
                              color: Colors.white.withOpacity(0.6),
                              fontSize: 16,
                            ),
                            prefixIcon: Icon(
                              Icons.search,
                              color: Colors.white.withOpacity(0.6),
                              size: 20,
                            ),
                            border: InputBorder.none,
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 12,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    GestureDetector(
                      onTap: _handleCreateNewSession,
                      child: Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: const Color(0xFF151415),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Center(
                          child: FaIcon(
                            FontAwesomeIcons.plus,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              // Content
              Expanded(
                child: sessionProvider.isLoadingSessions
                    ? const Center(
                        child: CircularProgressIndicator(
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : sessionProvider.sessions.isEmpty
                        ? _buildEmptyState()
                        : _buildSessionsList(sessionProvider),
              ),
            ],
          ),
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
          GestureDetector(
            onTap: _handleCreateNewSession,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FaIcon(FontAwesomeIcons.plus, size: 16, color: Colors.black),
                  SizedBox(width: 8),
                  Text(
                    'Start New Chat',
                    style: TextStyle(
                      color: Colors.black,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSessionsList(ChatSessionProvider sessionProvider) {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: sessionProvider.sessions.length,
      itemBuilder: (context, index) {
        final session = sessionProvider.sessions[index];
        final isSelected = session.id == sessionProvider.currentSessionId;
        final sessionColor = _getSessionColor(index);
        
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _handleSessionTap(session),
              onLongPress: sessionProvider.sessions.length > 1 
                  ? () => _handleDeleteSession(session)
                  : null,
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: isSelected ? const Color(0xFF2A282A) : const Color(0xFF151415),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 20,
                          height: 20,
                          decoration: BoxDecoration(
                            color: sessionColor,
                            shape: BoxShape.circle,
                          ),
                          child: Center(
                            child: Text(
                              session.displayTitle.isNotEmpty 
                                  ? session.displayTitle[0].toUpperCase()
                                  : 'C',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            session.displayTitle.isNotEmpty 
                                ? session.displayTitle 
                                : 'Chat Session',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (isSelected)
                          const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Padding(
                      padding: const EdgeInsets.only(left: 32),
                      child: Text(
                        _formatSessionTime(session.createdAt),
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
} 