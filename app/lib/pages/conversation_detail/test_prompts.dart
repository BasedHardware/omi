import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/ui/ui.dart';

class TestPromptsPage extends StatefulWidget {
  final ServerConversation conversation;

  /// Test seam for the prompt request; production uses [testConversationPrompt].
  final Future<String> Function(String prompt, String conversationId)? runPrompt;

  const TestPromptsPage({super.key, required this.conversation, this.runPrompt});

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
    final classic = _buildClassic(context);
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    return Scaffold(
        body: IosNativeSurface(
      title: l10n.testConversationPrompt,
      loading: loading,
      fallback: classic,
      toolbar: [
        NativeRow('test_prompt_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
        NativeRow('test_prompt_send', l10n.send, symbol: 'paperplane', enabled: !loading, action: (_) => onTap()),
      ],
      sections: [
        NativeSection('test_prompt', [
          // A draft longer than the native field takes keeps the complete Flutter page.
          NativeRow('test_prompt_input', l10n.prompt,
              kind: 'text',
              value: controller.text,
              maximumLength: _maximumPromptLength,
              action: (value) => setState(() => controller.text = value as String)),
        ]),
        if (result != '')
          NativeSection(
              'test_prompt_output',
              [
                NativeRow('test_prompt_result', result.replaceAll('**', ''), kind: 'label'),
              ],
              title: l10n.result),
      ],
    ));
  }

  static const _maximumPromptLength = 10000;

  Widget _buildClassic(BuildContext context) {
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

    var response = await (widget.runPrompt ?? testConversationPrompt)(controller.text, widget.conversation.id);
    print('response: $response');
    result = response.toString();
    if (!mounted) return;
    setState(() {
      loading = false;
    });
  }
}
