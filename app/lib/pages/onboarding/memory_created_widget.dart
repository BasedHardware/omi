import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/widgets/memory_list_item.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class MemoryCreatedWidget extends StatelessWidget {
  final VoidCallback goNext;
  const MemoryCreatedWidget({super.key, required this.goNext});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Text(
            'While you were talking, we created a memory for you. Isn\'t that cool?',
            style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          MemoryListItem(
              memory: context.read<SpeechProfileProvider>().memory!,
              updateMemory: (d, i) {},
              memoryIdx: 1,
              deleteMemory: (d, i) {}),
          SizedBox(height: 16),
          Container(
            width: double.infinity,
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
              onPressed: () {
                goNext();
              },
              child: const Text(
                'Awesome',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
