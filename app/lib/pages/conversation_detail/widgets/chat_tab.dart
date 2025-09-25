import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversation_chat.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/chat_input_area.dart';
import 'package:provider/provider.dart';

class ChatTab extends StatefulWidget {
  const ChatTab({super.key});

  @override
  State<ChatTab> createState() => _ChatTabState();
}

class _ChatTabState extends State<ChatTab> {
  final TextEditingController _messageController = TextEditingController();
  final FocusNode _messageFocusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();

  List<ConversationChatMessage> _messages = [];
  bool _isLoading = true;
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Register clear messages callback with provider
      final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
      provider.registerClearChatCallback(clearMessages);

      _loadMessages();
    });
  }

  @override
  void dispose() {
    _messageController.dispose();
    _messageFocusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _loadMessages() async {
    final provider = Provider.of<ConversationDetailProvider>(context, listen: false);
    try {
      final messages = await getConversationMessages(provider.conversation.id);
      if (mounted) {
        setState(() {
          _messages = messages.reversed.toList(); // Show latest at bottom
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('Error loading conversation messages: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // Public method to clear messages (can be called from outside)
  void clearMessages() {
    if (mounted) {
      setState(() {
        _messages.clear();
      });
    }
  }

  void _sendMessage(ConversationDetailProvider provider, String text) async {
    if (text.trim().isEmpty || _isSending) return;

    setState(() {
      _isSending = true;
    });

    // Add user message immediately to UI
    final userMessage = ConversationChatMessage(
      id: 'temp_${DateTime.now().millisecondsSinceEpoch}',
      text: text.trim(),
      createdAt: DateTime.now(),
      sender: 'human',
      conversationId: provider.conversation.id,
    );

    setState(() {
      _messages.add(userMessage);
    });

    _messageController.clear();
    _messageFocusNode.unfocus();
    _scrollToBottom();

    try {
      // Stream the AI response
      await for (var chunk in sendConversationMessageStream(provider.conversation.id, text.trim())) {
        if (chunk.type == MessageChunkType.data) {
          // TODO: Could add real-time streaming display here if needed
        } else if (chunk.type == MessageChunkType.done && chunk.message != null) {
          // Add final AI message
          final aiMessage = ConversationChatMessage(
            id: chunk.message!.id,
            text: chunk.message!.text,
            createdAt: chunk.message!.createdAt,
            sender: 'ai',
            conversationId: provider.conversation.id,
          );

          setState(() {
            _messages.add(aiMessage);
            _isSending = false;
          });
          _scrollToBottom();
          break;
        }
      }
    } catch (e) {
      debugPrint('Error sending message: $e');
      setState(() {
        _isSending = false;
      });
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        return Column(
          children: [
            // Chat messages area
            Expanded(
              child: GestureDetector(
                // Dismiss keyboard when tapping anywhere in messages area
                onTap: () {
                  FocusScope.of(context).unfocus();
                },
                child: _buildMessagesArea(provider),
              ),
            ),

            // Input area at bottom - reusing main chat structure
            ConversationChatInputArea(
              textController: _messageController,
              textFieldFocusNode: _messageFocusNode,
              isSending: _isSending,
              onSendMessage: (text) => _sendMessage(provider, text),
            ),
          ],
        );
      },
    );
  }

  Widget _buildMessagesArea(ConversationDetailProvider provider) {
    if (_isLoading) {
      return const SizedBox.expand(
        child: Center(
          child: CircularProgressIndicator(color: Colors.white54),
        ),
      );
    }

    if (_messages.isEmpty) {
      return _buildEmptyState();
    }

    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        // Chat messages
        SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              final message = _messages[index];
              return Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
                child: message.isFromUser ? _buildUserMessage(message) : _buildAIMessage(message),
              );
            },
            childCount: _messages.length,
          ),
        ),

        // Loading indicator when sending
        if (_isSending)
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Center(
                child: CircularProgressIndicator(color: Colors.white54),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildEmptyState() {
    return SizedBox.expand(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Colors.grey[900],
                  borderRadius: BorderRadius.circular(20),
                ),
                child: const Icon(
                  FontAwesomeIcons.solidComment,
                  color: Colors.white54,
                  size: 32,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Start a conversation',
                style: Theme.of(context).textTheme.titleMedium!.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                'Ask questions about this conversation',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                      color: Colors.grey.shade400,
                      height: 1.4,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUserMessage(ConversationChatMessage message) {
    return Padding(
      padding: const EdgeInsets.only(left: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            decoration: const BoxDecoration(
              color: Color(0xFF1f1f25),
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(16.0),
                topRight: Radius.circular(16.0),
                bottomRight: Radius.circular(4.0),
                bottomLeft: Radius.circular(16.0),
              ),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Text(
              message.text,
              style: const TextStyle(color: Colors.white, fontSize: 16),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAIMessage(ConversationChatMessage message) {
    return Padding(
      padding: const EdgeInsets.only(right: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            decoration: BoxDecoration(
              color: Colors.grey[900],
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(4.0),
                topRight: Radius.circular(16.0),
                bottomRight: Radius.circular(16.0),
                bottomLeft: Radius.circular(16.0),
              ),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Text(
              message.text,
              style: const TextStyle(color: Colors.white, fontSize: 16, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
