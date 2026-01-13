import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
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
  Future<void> _disconnect() async {
    final provider = context.read<TaskIntegrationProvider>();
    final navigator = Navigator.of(context);
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            context.l10n.disconnectFromApp(widget.appName),
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            context.l10n.disconnectFromAppDesc(widget.appName),
            style: const TextStyle(color: Color(0xFF8E8E93)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(
                context.l10n.cancel,
                style: const TextStyle(color: Color(0xFF8E8E93)),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(
                context.l10n.disconnect,
                style: const TextStyle(color: Colors.red),
              ),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {
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
      scaffoldMessenger.showSnackBar(
        SnackBar(
          content: Text(context.l10n.disconnectedFrom(widget.appName)),
          duration: const Duration(seconds: 2),
        ),
      );
      navigator.pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          context.l10n.appSettings(widget.appName),
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        actions: [
          if (widget.showRefresh)
            IconButton(
              icon: const Icon(Icons.refresh, color: Colors.white),
              onPressed: widget.onRefresh,
              tooltip: 'Refresh',
            ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                margin: const EdgeInsets.only(bottom: 24),
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.green.withOpacity(0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle, color: Colors.green, size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Connected to ${widget.appName}',
                        style: const TextStyle(
                          color: Colors.green,
                          fontSize: 14,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                context.l10n.account,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                widget.infoText ?? context.l10n.actionItemsSyncedTo(widget.appName),
                style: const TextStyle(
                  color: Color(0xFF8E8E93),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 32),
              // Wrap children in Expanded with SingleChildScrollView to handle overflow
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: widget.children,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              GestureDetector(
                onTap: _disconnect,
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red.withOpacity(0.3)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.logout,
                        color: Colors.red,
                        size: 20,
                      ),
                      const SizedBox(width: 12),
                      Text(
                        context.l10n.disconnectFromApp(widget.appName).replaceAll('?', ''),
                        style: const TextStyle(
                          color: Colors.red,
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
