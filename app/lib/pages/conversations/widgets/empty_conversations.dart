import 'package:flutter/material.dart';

class EmptyConversationsWidget extends StatefulWidget {
  const EmptyConversationsWidget({super.key});

  @override
  State<EmptyConversationsWidget> createState() => _EmptyConversationsWidgetState();
}

class _EmptyConversationsWidgetState extends State<EmptyConversationsWidget> {
  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 120.0),
      child: Text(
        'No conversations yet.',
        style: TextStyle(color: Colors.grey, fontSize: 16),
      ),
    );
  }
}
