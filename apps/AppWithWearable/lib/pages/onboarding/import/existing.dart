import 'package:flutter/material.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

class HasBackupPage extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback onSkip;

  const HasBackupPage({super.key, required this.goNext, required this.onSkip});

  @override
  State<HasBackupPage> createState() => _HasBackupPageState();
}

class _HasBackupPageState extends State<HasBackupPage> {
  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Padding(
          padding: EdgeInsets.all(32),
          child: Column(
            children: [
              Text(
                'Already had an account? Press "Import" to continue, otherwise press "Skip".',
                style: TextStyle(color: Colors.white, fontSize: 16, height: 1.5),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            MaterialButton(
              onPressed: widget.onSkip,
              child: const Text('Skip', style: TextStyle(decoration: TextDecoration.underline)),
            ),
            Container(
              decoration: BoxDecoration(
                border: const GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 2,
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: MaterialButton(
                onPressed: widget.goNext,
                child: const Text(
                  'Import',
                  style: TextStyle(color: Colors.white),
                ),
              ),
            ),
          ],
        ),
      ],
      // TODO: include an option for setting up backup
    );
  }
}
