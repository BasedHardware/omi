import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/openai.dart';
import 'package:friend_private/backend/schema/conversation.dart';

class TestPromptsPage extends StatefulWidget {
  final ServerConversation memory;

  const TestPromptsPage({super.key, required this.memory});

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
        title: const Text('Test Memory Prompt'),
        backgroundColor: Theme.of(context).colorScheme.primary,
        actions: [
          IconButton(
            onPressed: onTap,
            icon: const Icon(Icons.send),
          ),
        ],
      ),
      body: ListView(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'Prompt',
                labelStyle: TextStyle(color: Colors.white),
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
              : const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Result',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
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
    loading = true;
    var response = await triggerTestConversationPrompt(
      controller.text,
      widget.memory.getTranscript(generate: true),
    );
    print('response: $response');
    result = response.toString();
    setState(() {});
    loading = false;
  }
}
