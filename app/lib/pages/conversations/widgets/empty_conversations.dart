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
      padding: EdgeInsets.only(top: 240.0),
      child: Text(
        'No memories generated yet.',
        style: TextStyle(color: Colors.grey, fontSize: 16),
      ),
    );
  }
}
