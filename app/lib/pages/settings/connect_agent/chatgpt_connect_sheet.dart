import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/connect_agent/connect_agent_widgets.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one-tap ChatGPT path: opens Omi's approved listing in the ChatGPT app (or the browser). The
/// person approves there; the caller reloads its state when the app comes back to the foreground.
Future<void> showChatGptConnectSheet(BuildContext context) {
  return showOmiSheet<void>(
    context: context,
    builder: (context) => const ChatGptConnectSheet(),
  );
}

class ChatGptConnectSheet extends StatelessWidget {
  const ChatGptConnectSheet({super.key});

  Future<void> _open(BuildContext context) async {
    final opened = await launchUrl(chatGptDirectoryUrl, mode: LaunchMode.externalApplication);
    if (!context.mounted) return;
    if (opened) {
      Navigator.of(context).pop();
    } else {
      OmiFeedback.error(context, context.l10n.chatAppsCouldNotOpen(chatGptBrandName));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: OmiSpacing.sm),
          const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AgentMonogram('omi', size: 56),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: OmiSpacing.md),
                child: Icon(Icons.sync_alt, semanticLabel: null),
              ),
              AgentMonogram('GPT', size: 56),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(l10n.connectChatGptTitle, style: OmiType.title2, textAlign: TextAlign.center),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            l10n.connectChatGptSubtitle,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: OmiSpacing.xl),
          AgentSetupStep(number: 1, title: l10n.connectChatGptStepOpen, body: l10n.connectChatGptStepOpenBody),
          const SizedBox(height: OmiSpacing.md),
          AgentSetupStep(number: 2, title: l10n.connectChatGptStepApprove, body: l10n.connectChatGptStepApproveBody),
          const SizedBox(height: OmiSpacing.md),
          AgentSetupStep(number: 3, title: l10n.connectChatGptStepReturn, body: l10n.connectChatGptStepReturnBody),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const ValueKey('connect_chatgpt_open'),
            label: l10n.openChatGpt,
            icon: Icons.open_in_new,
            expand: true,
            onPressed: () => _open(context),
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
