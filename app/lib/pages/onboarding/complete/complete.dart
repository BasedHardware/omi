import 'package:flutter/material.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

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
      // TODO: improve UI on smaller devices
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        // const Center(
        //   child: Text(
        //     'You are all set  🎉',
        //     style: TextStyle(fontSize: 24, fontWeight: FontWeight.w500),
        //   ),
        // ),
        // const SizedBox(height: 32),
        // Padding(
        //   padding: const EdgeInsets.symmetric(horizontal: 16),
        //   child: RichText(
        //       text: const TextSpan(
        //     style: TextStyle(color: Colors.white, fontSize: 16, height: 1.5),
        //     children: [
        //       // TextSpan(text: 'Recommendations: \n\n', style: TextStyle(fontWeight: FontWeight.bold)),
        //       TextSpan(text: 'Avoid closing the app from the background. '),
        //       TextSpan(
        //           text: 'Keep the app running', style: TextStyle(decoration: TextDecoration.underline, fontSize: 18)),
        //       TextSpan(text: ' while using your Friend.'),
        //       TextSpan(text: '\n\n'),
        //       TextSpan(text: 'Make sure to '),
        //       TextSpan(
        //         text: 'enable notifications',
        //         style: TextStyle(decoration: TextDecoration.underline, fontSize: 18),
        //       ),
        //       TextSpan(text: ' to get the most out of your Friend.'),
        //     ],
        //   )),
        // ),
        const SizedBox(height: 40),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              Expanded(
                child: Container(
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
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                    onPressed: widget.goNext,
                    child: const Text(
                      'Get Started',
                      style: TextStyle(fontSize: 16),
                    ),
                  ),
                ),
              )
            ],
          ),
        ),
        const SizedBox(height: 16),
        // ElevatedButton()
      ],
    );
  }
}
