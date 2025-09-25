import 'package:flutter/material.dart';
import 'widgets/floating_chat_input.dart';
import 'widgets/floating_chat_messages.dart';

class FloatingChatPage extends StatelessWidget {
  const FloatingChatPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          // Placeholder for messages display, to be implemented in a future task
          const FloatingChatMessages(),
          // Placeholder for chat input, to be implemented in a future task
          const FloatingChatInput(),
        ],
      ),
    );
  }
}
