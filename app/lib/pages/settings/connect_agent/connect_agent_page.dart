import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/connect_agent/agent_key_sheet.dart';
import 'package:omi/pages/settings/connect_agent/chatgpt_connect_sheet.dart';
import 'package:omi/pages/settings/connect_agent/chatgpt_page.dart';
import 'package:omi/pages/settings/connect_agent/connect_agent_widgets.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Connect an Agent: ChatGPT in one tap, and agents with their own computer through a copy-paste
/// prompt that carries a one-time key link. Reloads when the app returns to the foreground, so a
/// ChatGPT approval made in the ChatGPT app shows up on return.
class ConnectAgentPage extends StatefulWidget {
  const ConnectAgentPage({super.key, this.service});

  /// Test seam; production uses the live API.
  final AgentConnectService? service;

  @override
  State<ConnectAgentPage> createState() => _ConnectAgentPageState();
}

class _ConnectAgentPageState extends State<ConnectAgentPage> with WidgetsBindingObserver {
  late final AgentConnectService _service = widget.service ?? AgentConnectService();
  AgentConnections? _connections;
  bool _failed = false;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load();
  }

  /// Reloads from the server. A failed reload after the first load keeps the list but says so,
  /// so a stale row is never shown as current without a word.
  Future<void> _load() async {
    // A reload that finishes after a newer one started must not overwrite the newer result.
    final generation = ++_loadGeneration;
    try {
      final connections = await _service.load();
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _connections = connections;
        _failed = false;
      });
    } catch (_) {
      if (!mounted || generation != _loadGeneration) return;
      if (_connections == null) {
        setState(() => _failed = true);
      } else {
        final l10n = context.l10n;
        OmiFeedback.error(context, l10n.connectAgentLoadFailed, actionLabel: l10n.tryAgain, onAction: _load);
      }
    }
  }

  Future<void> _openChatGpt() async {
    final connections = _connections;
    if (connections == null) return;
    if (connections.chatGptConnected && !connections.chatGptNeedsReconnect) {
      final disconnected = await routeToPage(context, ChatGptPage(service: _service, connections: connections));
      if (disconnected == true) {
        // The grants are gone whatever the reload says.
        if (mounted) setState(() => _connections = _connections?.withoutChatGpt());
        await _load();
      }
    } else {
      // A partial grant (needs reconnect) is still live: the sheet offers Disconnect for it.
      final disconnected = await showChatGptConnectSheet(context, service: _service, connections: connections);
      if (disconnected == true) {
        if (mounted) setState(() => _connections = _connections?.withoutChatGpt());
        await _load();
      }
    }
  }

  Future<void> _openAgent(ComputerAgent agent) async {
    final key = _connections?.agentKeys[agent];
    if (key == null) {
      await showAgentKeySheet(
        context,
        agent: agent,
        service: _service,
        onDiscarded: () {
          if (mounted) _load();
        },
      );
    } else {
      final revoked = await showActiveAgentSheet(
        context,
        agent: agent,
        keyId: key.id,
        lastUsedAt: key.lastUsedAt,
        service: _service,
      );
      // The key is gone whatever the reload says.
      if (revoked == true && mounted) setState(() => _connections = _connections?.withoutAgentKey(agent));
    }
    // A sheet may have made or revoked a key, whichever way it closed.
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final connections = _connections;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.connectAnAgent)),
      body: connections == null
          ? (_failed
              ? OmiErrorState(message: l10n.connectAgentLoadFailed, onRetry: _load, retryLabel: l10n.tryAgain)
              : const OmiLoadingState())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xxl),
                children: [
                  Text(l10n.connectAgentHeadline, style: OmiType.title2),
                  const SizedBox(height: OmiSpacing.sm),
                  Text(l10n.connectAgentIntro, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                  const SizedBox(height: OmiSpacing.xl),
                  OmiSettingsGroup(
                    header: l10n.connectAgentOneTap,
                    children: [
                      OmiSettingsRow(
                        key: const ValueKey('connect_agent_chatgpt'),
                        leading: const AgentMonogram('GPT'),
                        title: chatGptBrandName,
                        subtitle: connections.chatGptNeedsReconnect
                            ? l10n.chatGptNeedsReconnect
                            : (connections.chatGptConnected ? l10n.connected : null),
                        trailing: connections.chatGptNeedsReconnect
                            ? _connectButton(_openChatGpt, label: l10n.reconnect)
                            : (connections.chatGptConnected ? null : _connectButton(_openChatGpt)),
                        onTap: _openChatGpt,
                      ),
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.xl),
                  OmiSettingsGroup(
                    header: l10n.connectAgentComputerAgents,
                    headerSubtitle: l10n.connectAgentComputerAgentsSubtitle,
                    children: [
                      for (final agent in ComputerAgent.values) _agentRow(context, agent, connections),
                    ],
                  ),
                  const SizedBox(height: OmiSpacing.xl),
                  Center(
                    child: OmiButton.tertiary(
                      label: l10n.connectAgentDevelopers,
                      size: OmiButtonSize.compact,
                      icon: Icons.open_in_new,
                      onPressed: () => launchUrl(developerHomeUrl, mode: LaunchMode.externalApplication),
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _agentRow(BuildContext context, ComputerAgent agent, AgentConnections connections) {
    final l10n = context.l10n;
    final key = connections.agentKeys[agent];
    final name = agent.brandName ?? l10n.connectAgentOtherAgent;
    String? subtitle;
    if (key != null) {
      final lastUsed = key.lastUsedAt;
      // A key the agent has never used means the prompt was not run yet, not that it is connected.
      subtitle = lastUsed == null
          ? l10n.connectAgentWaiting
          : '${l10n.connectAgentKeyActive} · ${l10n.connectAgentLastUsed(OmiDateFormat.of(context).timestamp(lastUsed.toLocal()))}';
    }
    return OmiSettingsRow(
      key: ValueKey('connect_agent_${agent.name}'),
      leading: agent.brandName == null
          ? const AgentMonogram('', icon: Icons.terminal)
          : AgentMonogram(agent.brandName!.substring(0, 2)),
      title: name,
      subtitle: subtitle,
      trailing: key == null ? _connectButton(() => _openAgent(agent)) : null,
      onTap: () => _openAgent(agent),
    );
  }

  Widget _connectButton(VoidCallback onPressed, {String? label}) =>
      OmiButton(label: label ?? context.l10n.connect, size: OmiButtonSize.compact, onPressed: onPressed);
}
