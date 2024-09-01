import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/widgets/memory_list_item.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/speech_profile_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class MemoryCreatedWidget extends StatelessWidget {
  final VoidCallback goNext;
  const MemoryCreatedWidget({super.key, required this.goNext});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Consumer<SpeechProfileProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            provider.memory == null
                ? const SizedBox()
                : Text(
                    'Your first memory is ready! 🎉',
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
            const SizedBox(height: 16),
            context.read<SpeechProfileProvider>().memory == null
                ? const SizedBox()
                : MemoryListItem(
                    memory: context.read<SpeechProfileProvider>().memory!,
                    updateMemory: (d, i) {},
                    memoryIdx: 0,
                    deleteMemory: (d, i) {},
                    isFromOnboarding: true,
                  ),
            const SizedBox(height: 30),
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
                onPressed: () async {
                  // goNext();
                  MixpanelManager().memoryListItemClicked(provider.memory!, 0);
                  var result = await Navigator.of(context).push(MaterialPageRoute(
                    builder: (c) => MemoryDetailPage(
                      memory: provider.memory!,
                      isFromOnboarding: true,
                    ),
                  ));
                },
                child: const Text(
                  'Check it out',
                ),
              ),
            ),
          ],
        );
      }),
    );
  }
}
