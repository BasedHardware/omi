import 'package:flutter/material.dart';

class CompletePage extends StatefulWidget {
  final VoidCallback goNext;

  const CompletePage({super.key, required this.goNext});

  @override
  State<CompletePage> createState() => _CompletePageState();
}

class _CompletePageState extends State<CompletePage> {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const SizedBox(height: 40),
        const Text(
          'You are all set  🎉',
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 32),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: RichText(
              text: const TextSpan(
            style: TextStyle(color: Colors.white, fontSize: 16, height: 1.3),
            children: [
              // TextSpan(text: 'Recommendations: \n\n', style: TextStyle(fontWeight: FontWeight.bold)),
              TextSpan(text: 'Avoid closing the app from the background. '),
              TextSpan(
                  text: 'Keep the app running', style: TextStyle(decoration: TextDecoration.underline, fontSize: 18)),
              TextSpan(text: ' while using your Friend.'),
              TextSpan(text: '\n\n'),
              TextSpan(text: 'Make sure to '),
              TextSpan(
                text: 'enable notifications',
                style: TextStyle(decoration: TextDecoration.underline, fontSize: 18),
              ),
              TextSpan(text: ' to get the most out of your Friend.'),
            ],
          )),
        ),
        // CheckboxListTile(
        //   value: false,
        //   onChanged: (e) {},
        //   title: const Text(
        //     'Enable Notifications',
        //     style: TextStyle(fontSize: 18),
        //   ),
        //   checkboxShape: RoundedRectangleBorder(
        //     borderRadius: BorderRadius.circular(10),
        //   ),
        // ),
        const SizedBox(height: 32),
        MaterialButton(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
              // side: const BorderSide(color: Colors.white, width: 1),
            ),
            color: Colors.deepPurple,
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
            onPressed: widget.goNext,
            child: const Text('Get Started')),
        // ElevatedButton()
      ],
    );
  }
}
