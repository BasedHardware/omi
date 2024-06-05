import 'package:flutter/material.dart';

class CompletionTab extends StatefulWidget {
  const CompletionTab({super.key});

  @override
  State<CompletionTab> createState() => _CompletionTabState();
}

class _CompletionTabState extends State<CompletionTab> {
  @override
  Widget build(BuildContext context) {
    return const Column(children: [
      SizedBox(height: 48),
      Text(
        'Completed!',
        style: TextStyle(color: Colors.white, fontSize: 20),
      ),
      SizedBox(height: 24),
    ]);
  }
}
