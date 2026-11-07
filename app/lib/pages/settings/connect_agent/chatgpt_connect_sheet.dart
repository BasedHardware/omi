import 'package:flutter/material.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/connect_agent/connect_agent_widgets.dart';
import 'package:omi/services/agent_connect/agent_connections.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The one-tap ChatGPT path: opens Omi's approved listing in the ChatGPT app (or the browser). The
/// person approves there; the caller reloads its state when the app comes back to the foreground.
///
/// When ChatGPT already holds a grant that is missing access ([AgentConnections.chatGptNeedsReconnect]),
/// the sheet also offers Disconnect, so a partial grant can always be revoked from the app. Resolves
/// `true` after a disconnect.
Future<bool?> showChatGptConnectSheet(
  BuildContext context, {
  AgentConnectService? service,
  AgentConnections? connections,
  Future<bool> Function(Uri url)? urlLauncher,
  ValueChanged<AgentConnections>? onConnectionsLoaded,
}) {
  return showOmiSheet<bool>(
    context: context,
    builder: (context) => ChatGptConnectSheet(
      service: service,
      connections: connections,
      urlLauncher: urlLauncher,
      onConnectionsLoaded: onConnectionsLoaded,
    ),
  );
}

class ChatGptConnectSheet extends StatefulWidget {
  const ChatGptConnectSheet({
    super.key,
    this.service,
    this.connections,
    this.urlLauncher,
    this.onConnectionsLoaded,
  });

  final AgentConnectService? service;
  final AgentConnections? connections;
  final Future<bool> Function(Uri url)? urlLauncher;
  final ValueChanged<AgentConnections>? onConnectionsLoaded;

  @override
  State<ChatGptConnectSheet> createState() => _ChatGptConnectSheetState();
}

class _ChatGptConnectSheetState extends State<ChatGptConnectSheet> with WidgetsBindingObserver {
  bool _disconnecting = false;
  bool _checkingStatus = false;
  bool _handoffOpened = false;
  bool _launchFailed = false;
  String? _statusMessage;
  AgentConnections? _connections;

  @override
  void initState() {
    super.initState();
    _connections = widget.connections;
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _handoffOpened && widget.service != null) {
      _verifyConnection();
    }
  }

  Future<bool> _launch(Uri url) async {
    final launcher = widget.urlLauncher ?? ((uri) => launchUrl(uri, mode: LaunchMode.externalApplication));
    try {
      return await launcher(url);
    } catch (_) {
      return false;
    }
  }

  Future<void> _verifyConnection() async {
    final service = widget.service;
    if (service == null || _checkingStatus) return;
    setState(() => _checkingStatus = true);
    try {
      final latest = await service.load();
      widget.onConnectionsLoaded?.call(latest);
      if (!mounted) return;
      if (latest.chatGptConnected && !latest.chatGptNeedsReconnect) {
        Navigator.of(context).pop(false);
        return;
      }
      final l10n = context.l10n;
      setState(() {
        _connections = latest;
        _checkingStatus = false;
        _statusMessage =
            latest.chatGptNeedsReconnect ? l10n.chatGptNeedsReconnect : l10n.connectAgentWaitingTitle(chatGptBrandName);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _checkingStatus = false;
        _statusMessage = context.l10n.connectAgentLoadFailed;
      });
    }
  }

  Future<void> _disconnect() async {
    final service = widget.service;
    final connections = _connections;
    if (service == null || connections == null) return;
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
      await service.disconnectChatGpt(connections);
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() => _disconnecting = false);
      OmiFeedback.error(context, l10n.connectAgentActionFailed, actionLabel: l10n.tryAgain, onAction: _disconnect);
    }
  }

  Future<void> _open(BuildContext context) async {
    final openedPrimary = await _launch(chatGptDirectoryUrl);
    final openedFallback = !openedPrimary && await _launch(chatGptConnectorsUrl);
    if (!context.mounted) return;
    final l10n = context.l10n;
    if (openedPrimary || openedFallback) {
      setState(() {
        _handoffOpened = true;
        _launchFailed = false;
        _statusMessage = l10n.connectChatGptStepReturnBody;
      });
    } else {
      final errorText = l10n.chatAppsCouldNotOpen(chatGptBrandName);
      setState(() {
        _launchFailed = true;
        _statusMessage = errorText;
      });
      OmiFeedback.error(context, errorText);
    }
  }

  Future<void> _openConnectorsFallback(BuildContext context) async {
    final opened = await _launch(chatGptConnectorsUrl);
    if (!context.mounted) return;
    final l10n = context.l10n;
    if (opened) {
      setState(() {
        _handoffOpened = true;
        _launchFailed = false;
        _statusMessage = l10n.connectChatGptStepReturnBody;
      });
    } else {
      OmiFeedback.error(context, l10n.chatAppsCouldNotOpen(chatGptBrandName));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final canDisconnect = widget.service != null && (_connections?.chatGptConnected ?? false);
    final showFallback = _handoffOpened || _launchFailed;
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
          if (showFallback && _statusMessage != null) ...[
            const SizedBox(height: OmiSpacing.lg),
            Text(
              _statusMessage!,
              key: const ValueKey('connect_chatgpt_handoff_status'),
              style: OmiType.footnote.copyWith(
                color: _launchFailed ? OmiColors.error : OmiColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
          ],
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(
            key: const ValueKey('connect_chatgpt_open'),
            label: l10n.openChatGpt,
            icon: Icons.open_in_new,
            expand: true,
            onPressed: () => _open(context),
          ),
          if (showFallback) ...[
            const SizedBox(height: OmiSpacing.xs),
            OmiButton.secondary(
              key: const ValueKey('connect_chatgpt_open_connectors'),
              label: l10n.openSettings,
              icon: Icons.open_in_new,
              expand: true,
              onPressed: () => _openConnectorsFallback(context),
            ),
            if (widget.service != null) ...[
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                key: const ValueKey('connect_chatgpt_check_status'),
                label: l10n.refresh,
                expand: true,
                isLoading: _checkingStatus,
                onPressed: _checkingStatus ? null : _verifyConnection,
              ),
            ],
          ],
          if (canDisconnect) ...[
            const SizedBox(height: OmiSpacing.xs),
            OmiButton.destructive(
              key: const ValueKey('connect_chatgpt_disconnect'),
              label: l10n.disconnectChatGpt,
              expand: true,
              isLoading: _disconnecting,
              onPressed: _disconnecting ? null : _disconnect,
            ),
          ],
          const SizedBox(height: OmiSpacing.md),
        ],
      ),
    );
  }
}
