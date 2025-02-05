import 'package:flutter/material.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import 'widgets/chat_history_item.dart';
import 'widgets/empty_history.dart';
import 'widgets/new_chat_button.dart';

class ChatHistoryPage extends StatefulWidget {
  const ChatHistoryPage({super.key});

  @override
  State<ChatHistoryPage> createState() => _ChatHistoryPageState();
}

class _ChatHistoryPageState extends State<ChatHistoryPage> {
  @override
  void initState() {
    super.initState();
    // Load chat sessions when page opens
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MessageProvider>().loadChatSessions();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.surface,
        title: const Text('Chat History'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Consumer<MessageProvider>(
        builder: (context, provider, child) {
          if (provider.isLoadingSessions) {
            return const Center(child: CircularProgressIndicator());
          }

          return Column(
            children: [
              const NewChatButton(),
              Expanded(
                child: provider.chatSessions.isEmpty
                    ? const EmptyHistoryWidget()
                    : ListView.builder(
                        itemCount: provider.chatSessions.length,
                        itemBuilder: (context, index) {
                          final session = provider.chatSessions[index];
                          return ChatHistoryItem(
                            session: session,
                            onTap: () async {
                              Navigator.pop(context);
                              
                              context.read<MessageProvider>().loadChatSession(session.id).then((_) {
                                MixpanelManager().track('Chat Session Loaded');
                              });
                            },
                            onDelete: () async {
                              await provider.deleteChatSession(session.id);
                              MixpanelManager().track('Chat Session Deleted');
                            },
                            onRename: (newName) async {
                              await provider.renameChatSession(session.id, newName);
                              MixpanelManager().track('Chat Session Renamed');
                            },
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}