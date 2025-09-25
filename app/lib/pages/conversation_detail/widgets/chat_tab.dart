import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/conversation_chat.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
// Note: Using simplified message widgets for conversation chat
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
  bool _showVoiceRecorder = false;

  List<ConversationChatMessage> _messages = [];
  bool _isLoading = true;
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
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
              child: _buildMessagesArea(provider),
            ),

            // Input area at bottom
            _buildInputArea(provider),
          ],
        );
      },
    );
  }

  Widget _buildMessagesArea(ConversationDetailProvider provider) {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.white54),
      );
    }

    if (_messages.isEmpty) {
      return _buildEmptyState();
    }

    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        // Header
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(top: 24, left: 8, right: 8, bottom: 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: Text(
                    'Chat about this conversation',
                    style: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 24),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1,
                  ),
                ),
                IconButton(
                  onPressed: () async {
                    final success = await clearConversationChat(provider.conversation.id);
                    if (success && mounted) {
                      setState(() {
                        _messages.clear();
                      });
                    }
                  },
                  icon: const Icon(Icons.delete_outline, color: Colors.white, size: 20),
                ),
              ],
            ),
          ),
        ),

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
    return Center(
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
              'Ask questions about this conversation\nand get context-aware answers',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                    color: Colors.grey.shade400,
                    height: 1.4,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputArea(ConversationDetailProvider provider) {
    return Container(
      margin: const EdgeInsets.only(top: 10),
      decoration: const BoxDecoration(
        color: Color(0xFF1f1f25),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(22),
          topRight: Radius.circular(22),
        ),
      ),
      child: Column(
        children: [
          // Chat input row
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
            child: Row(
              children: [
                // Voice recorder button
                if (!_showVoiceRecorder)
                  GestureDetector(
                    onTap: () {
                      HapticFeedback.mediumImpact();
                      setState(() {
                        _showVoiceRecorder = true;
                      });
                    },
                    child: Container(
                      height: 44,
                      width: 44,
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: const Icon(
                        FontAwesomeIcons.microphone,
                        color: Colors.white,
                        size: 18,
                      ),
                    ),
                  ),

                const SizedBox(width: 8),

                // Text input
                Expanded(
                  child: _showVoiceRecorder
                      ? Container(
                          // TODO: Add VoiceRecorderWidget here
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.grey[800],
                            borderRadius: BorderRadius.circular(22),
                          ),
                          child: const Center(
                            child: Text(
                              'Voice recording...',
                              style: TextStyle(color: Colors.white54),
                            ),
                          ),
                        )
                      : Container(
                          decoration: BoxDecoration(
                            color: Colors.grey[800],
                            borderRadius: BorderRadius.circular(22),
                          ),
                          child: TextField(
                            controller: _messageController,
                            focusNode: _messageFocusNode,
                            decoration: const InputDecoration(
                              hintText: 'Ask about this conversation...',
                              hintStyle: TextStyle(fontSize: 16.0, color: Colors.white54),
                              focusedBorder: InputBorder.none,
                              enabledBorder: InputBorder.none,
                              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                              isDense: true,
                            ),
                            minLines: 1,
                            maxLines: 5,
                            keyboardType: TextInputType.multiline,
                            textCapitalization: TextCapitalization.sentences,
                            style: const TextStyle(fontSize: 16.0, color: Colors.white, height: 1.4),
                            onSubmitted: (text) => _sendMessage(provider, text),
                          ),
                        ),
                ),

                const SizedBox(width: 8),

                // Send button
                if (!_showVoiceRecorder)
                  ValueListenableBuilder<TextEditingValue>(
                    valueListenable: _messageController,
                    builder: (context, value, child) {
                      final canSend = value.text.trim().isNotEmpty && !_isSending;

                      return GestureDetector(
                        onTap: canSend
                            ? () {
                                HapticFeedback.mediumImpact();
                                _sendMessage(provider, _messageController.text);
                              }
                            : null,
                        child: Container(
                          height: 44,
                          width: 44,
                          decoration: BoxDecoration(
                            color: canSend
                                ? const Color(0xFF6C5CE7) // Purple accent color
                                : Colors.grey[700],
                            borderRadius: BorderRadius.circular(22),
                          ),
                          child: _isSending
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                    strokeWidth: 2,
                                  ),
                                )
                              : Icon(
                                  FontAwesomeIcons.paperPlane,
                                  color: canSend ? Colors.white : Colors.grey[500],
                                  size: 16,
                                ),
                        ),
                      );
                    },
                  ),
              ],
            ),
          ),

          // Safe area padding
          SizedBox(height: MediaQuery.of(context).padding.bottom + 8),
        ],
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
