import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/ui/ui.dart';

class TestPromptsPage extends StatefulWidget {
  final ServerConversation conversation;

  const TestPromptsPage({super.key, required this.conversation});

  @override
  State<TestPromptsPage> createState() => _TestPromptsPageState();
}

class _TestPromptsPageState extends State<TestPromptsPage> {
  TextEditingController controller = TextEditingController();
  String result = '';

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        title: Text(context.l10n.testConversationPrompt),
        backgroundColor: OmiColors.surface0,
        actions: [
          IconButton(
            onPressed: onTap,
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: OmiSpinner(),
                  )
                : const Icon(Icons.send),
          ),
        ],
      ),
      body: ListView(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: controller,
              decoration: InputDecoration(
                labelText: context.l10n.prompt,
                labelStyle: const TextStyle(color: Colors.white),
                border: const OutlineInputBorder(borderSide: BorderSide.none),
                contentPadding: const EdgeInsets.all(0),
              ),
              keyboardType: TextInputType.multiline,
              maxLines: 10,
              minLines: 1,
              autofocus: true,
            ),
          ),
          const SizedBox(height: 16),
          result == ''
              ? const SizedBox.shrink()
              : Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(context.l10n.result, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                ),
          result == ''
              ? const SizedBox.shrink()
              : Padding(padding: const EdgeInsets.all(16), child: Text(result.replaceAll('**', ''))),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  bool loading = false;

  onTap() async {
    if (loading) return;
    setState(() {
      loading = true;
    });

    var response = await testConversationPrompt(controller.text, widget.conversation.id);
    print('response: $response');
    result = response.toString();
    setState(() {
      loading = false;
    });
  }
}
