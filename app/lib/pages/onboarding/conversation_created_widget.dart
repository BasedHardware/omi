import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

Future updateConvoDetailProvider(BuildContext context, ServerConversation conversation) {
  return Future.microtask(() {
    context.read<ConversationProvider>().addConversation(conversation);
    var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, date);
  });
}

class ConversationCreatedWidget extends StatefulWidget {
  final VoidCallback goNext;

  const ConversationCreatedWidget({super.key, required this.goNext});

  @override
  State<ConversationCreatedWidget> createState() => _ConversationCreatedWidgetState();
}

class _ConversationCreatedWidgetState extends State<ConversationCreatedWidget> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await updateConvoDetailProvider(context, context.read<SpeechProfileProvider>().conversation!);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Consumer<SpeechProfileProvider>(builder: (context, provider, child) {
        return Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            provider.conversation == null
                ? const SizedBox()
                : Text(
                    'Your first conversation is ready! 🎉',
                    style: TextStyle(color: Colors.grey.shade300, fontSize: 18),
                    textAlign: TextAlign.center,
                  ),
            const SizedBox(height: 24),
            context.read<SpeechProfileProvider>().conversation == null
                ? const SizedBox()
                : ConversationListItem(
                    conversation: context.read<SpeechProfileProvider>().conversation!,
                    conversationIdx: 0,
                    isFromOnboarding: true,
                    date: DateTime(
                      provider.conversation!.createdAt.year,
                      provider.conversation!.createdAt.month,
                      provider.conversation!.createdAt.day,
                    ),
                  ),
            const SizedBox(height: 24),
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
                  // updateMemoryDetailProvider(context, provider.memory!);
                  MixpanelManager().conversationListItemClicked(provider.conversation!, 0);
                  routeToPage(
                      context, ConversationDetailPage(conversation: provider.conversation!, isFromOnboarding: true));
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
