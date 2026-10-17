import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/connect_agent/connect_agent_widgets.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// ChatGPT once connected: questions to try (each opens ChatGPT with it typed in) and Disconnect.
/// Pops `true` after a disconnect so the list reloads.
class ChatGptPage extends StatefulWidget {
  const ChatGptPage({super.key, required this.service, required this.connections});

  final AgentConnectService service;
  final AgentConnections connections;

  @override
  State<ChatGptPage> createState() => _ChatGptPageState();
}

class _ChatGptPageState extends State<ChatGptPage> {
  bool _disconnecting = false;

  Future<void> _ask(String question) async {
    final opened = await launchUrl(chatGptPromptUrl(question), mode: LaunchMode.externalApplication);
    if (!opened && mounted) OmiFeedback.error(context, context.l10n.chatAppsCouldNotOpen(chatGptBrandName));
  }

  Future<void> _disconnect() async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.disconnectChatGptQuestion,
      message: l10n.disconnectChatGptMessage,
      confirmLabel: l10n.disconnect,
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    setState(() => _disconnecting = true);
    try {
      await widget.service.disconnectChatGpt(widget.connections);
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _disconnecting = false);
      OmiFeedback.error(context, l10n.connectAgentActionFailed, actionLabel: l10n.tryAgain, onAction: _disconnect);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final examples = [l10n.chatGptExampleMeetings, l10n.chatGptExampleTasks, l10n.chatGptExampleGoals];
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: const Text(chatGptBrandName)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxl),
        children: [
          Row(
            children: [
              const AgentMonogram('GPT', size: 56),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(chatGptBrandName, style: OmiType.title2),
                    const SizedBox(height: OmiSpacing.xs),
                    Row(
                      children: [
                        Icon(Icons.check_circle, size: 16, color: OmiColors.success),
                        const SizedBox(width: OmiSpacing.xs),
                        Flexible(
                          child: Text(
                            l10n.chatGptConnectedEverywhere,
                            style: OmiType.subhead.copyWith(color: OmiColors.success),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiSettingsGroup(
            header: l10n.tryAskingChatGpt,
            footer: l10n.tryAskingChatGptFooter,
            children: [
              for (final example in examples)
                OmiSettingsRow(
                  title: example,
                  trailing: Icon(Icons.open_in_new, size: 18, color: OmiColors.textTertiary),
                  onTap: () => _ask(example),
                ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xxl),
          OmiButton.destructive(
            key: const ValueKey('chatgpt_disconnect'),
            label: l10n.disconnectChatGpt,
            expand: true,
            isLoading: _disconnecting,
            onPressed: _disconnecting ? null : _disconnect,
          ),
        ],
      ),
    );
  }
}
