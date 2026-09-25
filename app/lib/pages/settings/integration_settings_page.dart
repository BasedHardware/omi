import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class IntegrationSettingsPage extends StatefulWidget {
  final String appName;
  final String appKey;
  final Future<void> Function() disconnectService;
  final List<Widget> children;
  final bool showRefresh;
  final VoidCallback? onRefresh;
  final String? infoText;

  const IntegrationSettingsPage({
    super.key,
    required this.appName,
    required this.appKey,
    required this.disconnectService,
    this.children = const [],
    this.showRefresh = false,
    this.onRefresh,
    this.infoText,
  });

  @override
  State<IntegrationSettingsPage> createState() => _IntegrationSettingsPageState();
}

class _IntegrationSettingsPageState extends State<IntegrationSettingsPage> {
  bool _disconnecting = false;

  /// Confirms first, then shows the button's spinner only while the disconnect itself runs.
  Future<void> _disconnect() async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.disconnectFromApp(widget.appName),
      message: l10n.disconnectFromAppDesc(widget.appName),
      confirmLabel: l10n.disconnect,
      destructive: true,
    );
    if (!confirmed || !mounted) return;

    final provider = context.read<TaskIntegrationProvider>();
    final navigator = Navigator.of(context);
    setState(() => _disconnecting = true);
    try {
      await widget.disconnectService();
      if (!mounted) return;
      await provider.deleteConnection(widget.appKey);
      if (provider.selectedApp.key == widget.appKey) {
        final candidates = TaskIntegrationApp.values.where((app) {
          if (!app.isAvailable) return false;
          if (!PlatformService.isApple && app == TaskIntegrationApp.appleReminders) return false;
          if (app.key == widget.appKey) return false;
          return provider.isAppConnected(app);
        });
        final fallback = candidates.isNotEmpty ? candidates.first : null;
        if (fallback != null) {
          await provider.setSelectedApp(fallback);
          Logger.debug('Task integration disabled: ${widget.appName} - switched to ${fallback.key}');
        } else {
          Logger.debug('Task integration disabled: ${widget.appName} - no active integration selected');
        }
      }
      provider.refresh();
      if (!mounted) return;
      OmiFeedback.confirm(context, l10n.disconnectedFrom(widget.appName));
      navigator.pop();
    } finally {
      if (mounted) setState(() => _disconnecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.appSettings(widget.appName)),
        actions: [
          if (widget.showRefresh)
            OmiIconButton(icon: const Icon(Icons.refresh), label: context.l10n.refresh, onPressed: widget.onRefresh),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(OmiSpacing.sm),
                margin: const EdgeInsets.only(bottom: OmiSpacing.xl),
                decoration: BoxDecoration(
                  color: OmiColors.successSurface,
                  borderRadius: OmiRadius.smAll,
                  border: Border.all(color: OmiColors.success.withValues(alpha: 0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle, color: OmiColors.success, size: 16),
                    const SizedBox(width: OmiSpacing.xs),
                    Expanded(
                      child: Text(
                        context.l10n.connectedToApp(widget.appName),
                        style: OmiType.subhead.copyWith(color: OmiColors.success),
                      ),
                    ),
                  ],
                ),
              ),
              Text(context.l10n.account, style: OmiType.headline),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                widget.infoText ?? context.l10n.actionItemsSyncedTo(widget.appName),
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
              const SizedBox(height: OmiSpacing.xxl),
              // Wrap children in Expanded with SingleChildScrollView to handle overflow
              Expanded(
                child: SingleChildScrollView(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: widget.children),
                ),
              ),
              const SizedBox(height: OmiSpacing.md),
              OmiButton.destructive(
                label: context.l10n.disconnect,
                icon: Icons.logout,
                // Not the future: the button spins only while the disconnect runs, not while the
                // confirm dialog is open.
                onPressed: () => unawaited(_disconnect()),
                isLoading: _disconnecting,
                expand: true,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
