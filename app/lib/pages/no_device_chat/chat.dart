import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/providers/no_device_chat_provider.dart';
import 'package:friend_private/providers/no_device_onboarding_provider.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/no_device_chat/settings.dart';
import 'package:friend_private/services/twitter_api_service.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class NoDeviceChatScreen extends StatefulWidget {
  const NoDeviceChatScreen({super.key});

  @override
  State<NoDeviceChatScreen> createState() => _NoDeviceChatScreenState();
}

class _NoDeviceChatScreenState extends State<NoDeviceChatScreen> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  late NoDeviceOnboardingProvider _onboardingProvider;
  bool _initialized = false;
  final TwitterApiService _twitterService = TwitterApiService();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _initializeChat();
    });
  }

  Future<void> _initializeChat() async {
    if (!_initialized) {
      _onboardingProvider = context.read<NoDeviceOnboardingProvider>();
      final currentUser = FirebaseAuth.instance.currentUser;
      if (currentUser != null) {
        final token = await getIdToken();
        if (token != null) {
          await _loadMessageSummary();
        }
      }
      
      FirebaseAuth.instance.authStateChanges().listen((User? user) {
        if (user != null && mounted) {
          _loadMessageSummary();
        }
      });
    }
  }

  Future<void> _loadMessageSummary() async {
    try {
      final messages = await _twitterService.getStoredMessages();
      final conversationGroups = <String, List<Map<String, dynamic>>>{};
      for (var message in messages) {
        final participantKey = (message['participant_ids'] as List).join('-');
        if (!conversationGroups.containsKey(participantKey)) {
          conversationGroups[participantKey] = [];
        }
        conversationGroups[participantKey]!.add(message);
      }

      final totalMessages = messages.length;
      final totalConversations = conversationGroups.length;
      final latestMessageDate = messages.isNotEmpty 
          ? DateTime.parse(messages.first['created_at']) 
          : null;

      String summaryMessage = 'Hey @${_onboardingProvider.twitterHandle.replaceAll('@', '')}! Here\'s your X DMs summary:\n\n';
      summaryMessage += '📨 Total Messages: $totalMessages\n';
      summaryMessage += '💬 Active Conversations: $totalConversations\n';
      
      if (latestMessageDate != null) {
        final now = DateTime.now();
        final difference = now.difference(latestMessageDate);
        String timeAgo;
        if (difference.inDays > 0) {
          timeAgo = '${difference.inDays} days';
        } else if (difference.inHours > 0) {
          timeAgo = '${difference.inHours} hours';
        } else {
          timeAgo = '${difference.inMinutes} minutes';
        }
        summaryMessage += '🕒 Latest Message: $timeAgo ago';
      }

      if (mounted) {
        context.read<NoDeviceChatProvider>().addMessage(
          ServerMessage(
            '1',
            DateTime.now(),
            summaryMessage,
            MessageSender.ai,
            MessageType.text,
            null,
            false,
            [],
          ),
        );
        setState(() => _initialized = true);
      }
    } catch (e) {
      if (mounted) {
        context.read<NoDeviceChatProvider>().addMessage(
          ServerMessage(
            '1',
            DateTime.now(),
            'Hey @${_onboardingProvider.twitterHandle.replaceAll('@', '')}! Welcome to your X DMs summary.',
            MessageSender.ai,
            MessageType.text,
            null,
            false,
            [],
          ),
        );
        setState(() => _initialized = true);
      }
    }
  }

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _sendMessage() async {
    if (_messageController.text.trim().isEmpty) return;
    
    final provider = context.read<NoDeviceChatProvider>();
    final text = _messageController.text;
    _messageController.clear();
    
    MixpanelManager().chatMessageSent(text);
    await provider.sendMessageToServer(text);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          0.0,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.add, color: Colors.white),
          onPressed: () {},
        ),
        title: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white.withOpacity(0.2)),
              ),
              child: ClipOval(
                child: Image.asset(
                  'assets/images/herologo.png',
                  width: 24,
                  height: 24,
                ),
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              'omi',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings, color: Colors.white),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const SettingsScreen(),
                ),
              );
            },
          ),
        ],
      ),
      body: Consumer<NoDeviceChatProvider>(
        builder: (context, provider, child) {
          return GestureDetector(
            onTap: () => FocusScope.of(context).unfocus(),
            child: Column(
              children: [
                Expanded(
                  child: ListView.builder(
                    reverse: true,
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    itemCount: provider.messages.length + (provider.showTypingIndicator ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (provider.showTypingIndicator && index == 0) {
                        return _buildTypingIndicator();
                      }
                      final message = provider.messages[provider.showTypingIndicator ? index - 1 : index];
                      return _buildMessageBubble(message);
                    },
                  ),
                ),
                _buildMessageInput(),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildMessageBubble(ServerMessage message) {
    final isBot = message.sender == MessageSender.ai;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment: isBot ? MainAxisAlignment.start : MainAxisAlignment.end,
        children: [
          if (isBot) ...[
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white.withOpacity(0.2)),
              ),
              child: ClipOval(
                child: Image.asset(
                  'assets/images/herologo.png',
                  width: 24,
                  height: 24,
                ),
              ),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: isBot ? Colors.grey[900] : Colors.blue,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                message.text,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTypingIndicator() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white.withOpacity(0.2)),
            ),
            child: ClipOval(
              child: Image.asset(
                'assets/images/herologo.png',
                width: 24,
                height: 24,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: Colors.grey[900],
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildDot(0),
                _buildDot(1),
                _buildDot(2),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDot(int index) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 2),
      width: 6,
      height: 6,
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.5),
        shape: BoxShape.circle,
      ),
    );
  }

  Widget _buildMessageInput() {
    return Container(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        top: 8,
        bottom: MediaQuery.of(context).padding.bottom + 8,
      ),
      decoration: BoxDecoration(
        color: Colors.black,
        border: Border(
          top: BorderSide(
            color: Colors.white.withOpacity(0.1),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              constraints: const BoxConstraints(maxHeight: 120),
              decoration: BoxDecoration(
                color: Colors.grey[900],
                borderRadius: BorderRadius.circular(24),
              ),
              child: TextFormField(
                controller: _messageController,
                style: const TextStyle(color: Colors.white),
                maxLines: null,
                keyboardType: TextInputType.multiline,
                textInputAction: TextInputAction.newline,
                decoration: const InputDecoration(
                  hintText: 'Type a response',
                  hintStyle: TextStyle(color: Colors.grey),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(vertical: 12),
                  isDense: true,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: Colors.blue,
              borderRadius: BorderRadius.circular(24),
            ),
            child: IconButton(
              icon: const Icon(Icons.send, color: Colors.white),
              onPressed: _sendMessage,
            ),
          ),
        ],
      ),
    );
  }
}
