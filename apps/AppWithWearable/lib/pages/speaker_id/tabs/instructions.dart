import 'package:flutter/material.dart';

class InstructionsTab extends StatefulWidget {
  const InstructionsTab({super.key});

  @override
  State<InstructionsTab> createState() => _InstructionsTabState();
}

class _InstructionsTabState extends State<InstructionsTab> {
  @override
  Widget build(BuildContext context) {
    return const Column(children: [
      SizedBox(height: 48),
      Text(
        'Setup Your Speaker Profile',
        style: TextStyle(color: Colors.white, fontSize: 20),
      ),
      SizedBox(height: 24),
      Text('Instructions ....', style: TextStyle(color: Colors.white),),
      SizedBox(height: 24),

    ]);
  }
}
