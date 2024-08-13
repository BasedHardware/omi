import 'package:flutter/material.dart';

class EmptyMemoriesWidget extends StatefulWidget {
  const EmptyMemoriesWidget({super.key});

  @override
  State<EmptyMemoriesWidget> createState() => _EmptyMemoriesWidgetState();
}

class _EmptyMemoriesWidgetState extends State<EmptyMemoriesWidget> {
  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 200.0),
      child: Text(
        'No memories generated yet.',
        style: TextStyle(color: Colors.grey, fontSize: 16),
      ),
    );
  }
}
