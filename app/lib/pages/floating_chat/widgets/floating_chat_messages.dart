import 'package:flutter/material.dart';

class FloatingChatMessages extends StatelessWidget {
  const FloatingChatMessages({super.key});

  @override
  Widget build(BuildContext context) {
    // TODO: Replace with actual message list from a provider
    return Expanded(
      child: ListView(
        children: const [
          // Placeholder messages
          ListTile(title: Text('Hello!')),
          ListTile(title: Text('How can I help you today?')),
        ],
      ),
    );
  }
}
