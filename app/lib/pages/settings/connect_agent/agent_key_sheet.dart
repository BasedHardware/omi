import 'package:flutter/material.dart';

import 'package:omi/pages/settings/connect_agent/connect_agent_widgets.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Connects an agent that runs on its own computer. The sheet previews the prompt; the key and its
/// one-time link are made only on Copy Prompt, so opening and closing the sheet creates nothing.
Future<void> showAgentKeySheet(
  BuildContext context, {
  required ComputerAgent agent,
  required AgentConnectService service,
  VoidCallback? onDiscarded,
}) {
  return showOmiSheet<void>(
    context: context,
    builder: (context) => AgentKeySheet(agent: agent, service: service, onDiscarded: onDiscarded),
  );
}

class AgentKeySheet extends StatefulWidget {
  const AgentKeySheet({super.key, required this.agent, required this.service, this.onDiscarded});

  final ComputerAgent agent;
  final AgentConnectService service;

  /// Called after a key made for a sheet that has since closed is revoked, so the list catches up.
  final VoidCallback? onDiscarded;

  @override
  State<AgentKeySheet> createState() => _AgentKeySheetState();
}

class _AgentKeySheetState extends State<AgentKeySheet> {
  PreparedAgentPrompt? _prepared;
  bool _working = false;

  /// First tap makes the key and link and copies; later taps copy the same prompt again.
  Future<void> _copy() async {
    final prepared = _prepared;
    if (prepared != null) {
      await OmiClipboard.copy(context, prepared.prompt, what: context.l10n.prompt);
      return;
    }
    await _makeAndCopy();
  }

  /// A fresh link replaces the previous key only once it has been copied
  /// ([AgentConnectService.retireOlderKeys]); if making it fails or the sheet closes first, the
  /// previous prompt and key stay as they were.
  Future<void> _newLink() => _makeAndCopy();

  Future<void> _makeAndCopy() async {
    final l10n = context.l10n;
    setState(() => _working = true);
    try {
      final prepared = await widget.service.preparePrompt(widget.agent);
      if (!mounted) {
        // Closed while the link was being made: nobody received it, so its key must not linger.
        final onDiscarded = widget.onDiscarded;
        widget.service.revokeKey(prepared.keyId).then((_) => onDiscarded?.call(), onError: (_) {});
        return;
      }
      setState(() => _prepared = prepared);
      await OmiClipboard.copy(context, prepared.prompt, what: l10n.prompt);
      // The new prompt is in hand, so the key it replaces (an earlier link, or one a stale list
      // missed) can go now, and only now. The buttons stay busy until it is done, so a second
      // "new link" cannot race this one and revoke each other's keys.
      await widget.service.retireOlderKeys(widget.agent, prepared.keyId);
      if (mounted) setState(() => _working = false);
    } catch (_) {
      if (!mounted) {
        // Closed while the link was being made and the link then failed: preparePrompt already
        // deleted the key it made, but the list behind the sheet reloaded while that key existed
        // and would keep showing it as waiting for the agent.
        widget.onDiscarded?.call();
        return;
      }
      setState(() => _working = false);
      OmiFeedback.error(context, l10n.connectAgentPrepareFailed, actionLabel: l10n.tryAgain, onAction: _copy);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final agent = widget.agent;
    final name = agent.brandName;
    final prepared = _prepared;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: OmiSpacing.sm),
          Row(
            children: [
              name == null
                  ? const AgentMonogram('', icon: Icons.terminal, size: 48)
                  : AgentMonogram(name.substring(0, 2), size: 48),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name == null ? l10n.connectAgentOtherAgent : l10n.connectAgentNamed(name),
                      style: OmiType.title3,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      name == null ? l10n.connectAgentGenericPromptSubtitle : l10n.connectAgentPromptSubtitle(name),
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          if (prepared != null) ...[
            Container(
              padding: const EdgeInsets.all(OmiSpacing.md),
              decoration: BoxDecoration(color: OmiColors.successSurface, borderRadius: OmiRadius.mdAll),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.lock_outline, size: 20, color: OmiColors.success),
                  const SizedBox(width: OmiSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          l10n.connectAgentKeyCreated(agent.keyName),
                          style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 2),
                        Text(l10n.connectAgentKeyCreatedBody, style: OmiType.footnote),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
          OmiSectionHeader(l10n.prompt),
          AgentPromptPreview(prompt: prepared?.prompt ?? widget.service.previewPrompt()),
          const SizedBox(height: OmiSpacing.lg),
          OmiButton(
            key: const ValueKey('agent_key_copy_prompt'),
            label: l10n.copyPrompt,
            icon: Icons.copy,
            expand: true,
            isLoading: _working,
            onPressed: _working ? null : _copy,
          ),
          if (prepared != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            OmiButton.tertiary(
              key: const ValueKey('agent_key_new_link'),
              label: l10n.connectAgentNewLink,
              expand: true,
              onPressed: _working ? null : _newLink,
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}

/// An agent that already holds a key: when it was last used, and Revoke. Resolves `true` after a
/// revoke.
Future<bool?> showActiveAgentSheet(
  BuildContext context, {
  required ComputerAgent agent,
  required String keyId,
  required DateTime? lastUsedAt,
  required AgentConnectService service,
}) {
  return showOmiSheet<bool>(
    context: context,
    builder: (context) => ActiveAgentSheet(agent: agent, keyId: keyId, lastUsedAt: lastUsedAt, service: service),
  );
}

class ActiveAgentSheet extends StatefulWidget {
  const ActiveAgentSheet({
    super.key,
    required this.agent,
    required this.keyId,
    required this.lastUsedAt,
    required this.service,
  });

  final ComputerAgent agent;
  final String keyId;
  final DateTime? lastUsedAt;
  final AgentConnectService service;

  @override
  State<ActiveAgentSheet> createState() => _ActiveAgentSheetState();
}

class _ActiveAgentSheetState extends State<ActiveAgentSheet> {
  bool _revoking = false;

  String get _name => widget.agent.brandName ?? context.l10n.connectAgentOtherAgent;

  Future<void> _revoke() async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.revokeAgentKeyQuestion(_name),
      message: l10n.revokeAgentKeyMessage(_name),
      confirmLabel: l10n.revoke,
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    setState(() => _revoking = true);
    try {
      await widget.service.revokeAgent(widget.agent, shownKeyId: widget.keyId);
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _revoking = false);
      OmiFeedback.error(context, l10n.connectAgentActionFailed, actionLabel: l10n.tryAgain, onAction: _revoke);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final lastUsed = widget.lastUsedAt;
    final brand = widget.agent.brandName;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: OmiSpacing.sm),
          Row(
            children: [
              brand == null
                  ? const AgentMonogram('', icon: Icons.terminal, size: 48)
                  : AgentMonogram(brand.substring(0, 2), size: 48),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      lastUsed == null ? l10n.connectAgentWaitingTitle(_name) : l10n.connectAgentActiveTitle(_name),
                      style: OmiType.title3,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      lastUsed == null
                          ? l10n.connectAgentWaiting
                          : l10n.connectAgentLastUsed(OmiDateFormat.of(context).timestamp(lastUsed.toLocal())),
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.lg),
          Text(l10n.connectAgentActiveBody(_name), style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: OmiSpacing.xl),
          OmiButton.destructive(
            key: const ValueKey('agent_key_revoke'),
            label: l10n.revoke,
            expand: true,
            isLoading: _revoking,
            onPressed: _revoking ? null : _revoke,
          ),
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
