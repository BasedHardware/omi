import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/settings/connect_agent/chatgpt_connect_sheet.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/services/agent_connect/agent_prompts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ask an AI app about one conversation without pasting it: the question names the conversation and
/// the app looks it up through its Omi connector. ChatGPT opens with the question typed in once it
/// is connected; Copy works for any app. Pops `true` when the person chose to connect ChatGPT first.
Future<void> showAskAgentSheet(BuildContext context, ServerConversation conversation,
    {AgentConnectService? service}) async {
  final connectFirst = await showOmiSheet<bool>(
    context: context,
    title: context.l10n.askAboutConversation,
    builder: (context) => AskAgentSheet(conversation: conversation, service: service ?? AgentConnectService()),
  );
  // Connecting is its own sheet; it opens from the page once this one has closed.
  if (connectFirst == true && context.mounted) await showChatGptConnectSheet(context);
}

class AskAgentSheet extends StatefulWidget {
  const AskAgentSheet({super.key, required this.conversation, required this.service});

  final ServerConversation conversation;
  final AgentConnectService service;

  @override
  State<AskAgentSheet> createState() => _AskAgentSheetState();
}

class _AskAgentSheetState extends State<AskAgentSheet> {
  final _question = TextEditingController();
  bool? _chatGptConnected;

  @override
  void initState() {
    super.initState();
    widget.service.chatGptConnected().then(
      (connected) {
        if (mounted) setState(() => _chatGptConnected = connected);
      },
      onError: (_) {
        // Unknown counts as not connected: the sheet offers Connect, which is harmless if it is.
        if (mounted) setState(() => _chatGptConnected = false);
      },
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_question.text.isEmpty) _question.text = context.l10n.askSuggestFollowUp;
  }

  @override
  void dispose() {
    _question.dispose();
    super.dispose();
  }

  String _prompt() {
    final conversation = widget.conversation;
    return buildConversationQuestionPrompt(
      conversationId: conversation.id,
      title: conversation.structured.title,
      date: OmiDateFormat.of(context).date(conversation.createdAt.toLocal()),
      question: _question.text,
    );
  }

  Future<void> _askChatGpt() async {
    final opened = await launchUrl(chatGptPromptUrl(_prompt()), mode: LaunchMode.externalApplication);
    if (!mounted) return;
    if (opened) {
      Navigator.of(context).pop();
    } else {
      OmiFeedback.error(context, context.l10n.chatAppsCouldNotOpen('ChatGPT'));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final suggestions = [l10n.askSuggestFollowUp, l10n.askSuggestCommitments, l10n.askSuggestDoc];
    final connected = _chatGptConnected;
    final hasQuestion = _question.text.trim().isNotEmpty;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l10n.askAboutConversationSubtitle, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
        const SizedBox(height: OmiSpacing.lg),
        TextField(
          key: const ValueKey('ask_agent_question'),
          controller: _question,
          minLines: 2,
          maxLines: 4,
          textCapitalization: TextCapitalization.sentences,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(labelText: l10n.askYourQuestion),
        ),
        const SizedBox(height: OmiSpacing.md),
        Wrap(
          spacing: OmiSpacing.sm,
          runSpacing: OmiSpacing.sm,
          children: [
            for (final suggestion in suggestions)
              OmiFilterChip(
                label: suggestion,
                selected: _question.text == suggestion,
                onSelected: () => setState(() => _question.text = suggestion),
              ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        if (connected == null)
          const Center(child: OmiSpinner())
        else if (connected)
          OmiButton(
            key: const ValueKey('ask_agent_chatgpt'),
            label: l10n.askInChatGpt,
            icon: Icons.open_in_new,
            expand: true,
            onPressed: hasQuestion ? _askChatGpt : null,
          )
        else ...[
          Text(
            l10n.askConnectChatGptFirst,
            textAlign: TextAlign.center,
            style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: OmiSpacing.sm),
          OmiButton(
            key: const ValueKey('ask_agent_connect_chatgpt'),
            label: l10n.connectChatGptTitle,
            expand: true,
            onPressed: () => Navigator.of(context).pop(true),
          ),
        ],
        const SizedBox(height: OmiSpacing.sm),
        OmiButton.secondary(
          key: const ValueKey('ask_agent_copy'),
          label: l10n.copyForAnyApp,
          icon: Icons.copy,
          expand: true,
          onPressed: hasQuestion ? () => OmiClipboard.copy(context, _prompt(), what: l10n.prompt) : null,
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}
