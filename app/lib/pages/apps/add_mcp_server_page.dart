import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class AddMcpServerPage extends StatefulWidget {
  const AddMcpServerPage({super.key});

  @override
  State<AddMcpServerPage> createState() => _AddMcpServerPageState();
}

class _AddMcpServerPageState extends State<AddMcpServerPage> {
  final _nameController = TextEditingController();
  final _urlController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  bool _isLoading = false;
  bool _isPolling = false;
  String? _appId;
  Timer? _pollTimer;

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    _descriptionController.dispose();
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _connect() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    final result = await addMcpServer(
      _nameController.text.trim(),
      _urlController.text.trim(),
      description: _descriptionController.text.trim(),
    );

    if (!mounted) return;
    setState(() => _isLoading = false);

    if (result == null) {
      _showError(context.l10n.mcpConnectionFailed);
      return;
    }

    if (result.containsKey('error')) {
      _showError(result['error'] as String);
      return;
    }

    _appId = result['app_id'] as String?;
    final requiresOauth = result['requires_oauth'] as bool? ?? false;

    if (requiresOauth) {
      final authUrl = result['auth_url'] as String?;
      if (authUrl != null) {
        await _openAuthInAppBrowser(authUrl);
      } else {
        _showError(context.l10n.mcpConnectionFailed);
      }
    } else {
      final toolsCount = result['tools_count'] as int? ?? 0;
      if (mounted) {
        try {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.mcpServerConnected(toolsCount)),
              backgroundColor: Colors.green,
            ),
          );
        } catch (_) {}
        _navigateToAppDetail(_appId!);
      }
    }
  }

  Future<void> _openAuthInAppBrowser(String authUrl) async {
    final uri = Uri.parse(authUrl);
    try {
      await launchUrl(uri, mode: LaunchMode.inAppBrowserView);
    } on PlatformException {
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } on PlatformException {
        if (mounted) _showError(context.l10n.mcpConnectionFailed);
        return;
      }
    }

    // Start polling for OAuth completion
    _startPollingForCompletion();
  }

  void _startPollingForCompletion() {
    if (_appId == null) return;
    setState(() => _isPolling = true);

    int attempts = 0;
    const maxAttempts = 100; // ~5 minutes at 3s intervals

    _pollTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      attempts++;
      if (attempts > maxAttempts || !mounted) {
        timer.cancel();
        if (mounted) {
          setState(() => _isPolling = false);
          _showError(context.l10n.mcpConnectionFailed);
        }
        return;
      }

      final appData = await getAppDetailsServer(_appId!);
      if (appData == null) return;

      final status = appData['status'] as String?;
      if (status == 'approved') {
        timer.cancel();
        final chatTools = appData['chat_tools'] as List?;
        final toolsCount = chatTools?.length ?? 0;
        if (mounted) {
          setState(() => _isPolling = false);
          try {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(context.l10n.mcpServerConnected(toolsCount)),
                backgroundColor: Colors.green,
              ),
            );
            final app = App.fromJson(appData);
            Navigator.pop(context);
            routeToPage(context, AppDetailPage(app: app));
          } catch (_) {}
        }
      }
    });
  }

  Future<void> _navigateToAppDetail(String appId) async {
    final appData = await getAppDetailsServer(appId);
    if (!mounted) return;
    if (appData != null) {
      final app = App.fromJson(appData);
      Navigator.pop(context);
      routeToPage(context, AppDetailPage(app: app));
    } else {
      Navigator.pop(context, true);
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    try {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: Colors.red),
      );
    } catch (_) {
      // Widget may be deactivated during async navigation
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.surface,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.surface,
        title: Text(context.l10n.addMcpServer, style: const TextStyle(fontSize: 18)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.connectExternalAiTools,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: Colors.white.withOpacity(0.7),
                    ),
              ),
              const SizedBox(height: 32),
              TextFormField(
                controller: _nameController,
                decoration: InputDecoration(
                  labelText: context.l10n.appName,
                  hintText: 'e.g. Mixpanel Analytics',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withOpacity(0.3)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Colors.white, width: 1.5),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return context.l10n.appName;
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _descriptionController,
                decoration: InputDecoration(
                  labelText: context.l10n.descriptionOptional,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withOpacity(0.3)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Colors.white, width: 1.5),
                  ),
                ),
                maxLines: 2,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _urlController,
                decoration: InputDecoration(
                  labelText: context.l10n.mcpServerUrl,
                  hintText: 'https://mcp.example.com/sse',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withOpacity(0.3)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: Colors.white, width: 1.5),
                  ),
                ),
                keyboardType: TextInputType.url,
                autocorrect: false,
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return context.l10n.mcpServerUrl;
                  }
                  final uri = Uri.tryParse(value.trim());
                  if (uri == null || !uri.hasScheme || !uri.host.contains('.')) {
                    return context.l10n.mcpServerUrl;
                  }
                  return null;
                },
              ),
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: (_isLoading || _isPolling) ? null : _connect,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: (_isLoading || _isPolling)
                      ? Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                            ),
                            if (_isPolling) ...[
                              const SizedBox(width: 12),
                              Text(context.l10n.authorizingMcpServer,
                                  style: const TextStyle(fontSize: 14, color: Colors.black)),
                            ],
                          ],
                        )
                      : Text(context.l10n.connect, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
