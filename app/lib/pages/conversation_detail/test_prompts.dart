import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/api/conversations.dart';

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
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.testConversationPrompt),
        backgroundColor: Theme.of(context).colorScheme.primary,
        actions: [
          IconButton(
            onPressed: onTap,
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      color: Colors.white,
                      strokeWidth: 2.0,
                    ),
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
                border: OutlineInputBorder(borderSide: BorderSide.none),
                contentPadding: EdgeInsets.all(0),
              ),
              keyboardType: TextInputType.multiline,
              maxLines: 10,
              minLines: 1,
              autofocus: true,
            ),
          ),
          const SizedBox(
            height: 16,
          ),
          result == ''
              ? const SizedBox.shrink()
              : Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    context.l10n.result,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
                  ),
                ),
          result == ''
              ? const SizedBox.shrink()
              : Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(result.replaceAll('**', '')),
                ),
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

    var response = await testConversationPrompt(
      controller.text,
      widget.conversation.id,
    );
    print('response: $response');
    result = response.toString();
    setState(() {
      loading = false;
    });
  }
}
