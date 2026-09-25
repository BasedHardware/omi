import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'widgets/app_form_fields.dart';

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
        OmiFeedback.confirm(context, context.l10n.mcpServerConnected(toolsCount));
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
          OmiFeedback.confirm(context, context.l10n.mcpServerConnected(toolsCount));
          final app = App.fromJson(appData);
          Navigator.pop(context);
          routeToPage(context, AppDetailPage(app: app));
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
    OmiFeedback.error(context, message);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        backgroundColor: OmiColors.surface0,
        title: Text(l10n.addMcpServer, style: OmiType.body),
        leading: const OmiBackButton(),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(OmiSpacing.xl),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                l10n.connectExternalAiTools,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary),
              ),
              const SizedBox(height: OmiSpacing.xxl),
              TextFormField(
                controller: _nameController,
                decoration: appFormInputDecoration(label: l10n.appName, hint: 'e.g. Mixpanel Analytics'),
                style: const TextStyle(color: OmiColors.textPrimary),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return l10n.appName;
                  }
                  return null;
                },
              ),
              const SizedBox(height: OmiSpacing.md),
              TextFormField(
                controller: _descriptionController,
                decoration: appFormInputDecoration(label: l10n.descriptionOptional),
                style: const TextStyle(color: OmiColors.textPrimary),
                maxLines: 2,
              ),
              const SizedBox(height: OmiSpacing.md),
              TextFormField(
                controller: _urlController,
                decoration: appFormInputDecoration(label: l10n.mcpServerUrl, hint: 'https://mcp.example.com/sse'),
                style: const TextStyle(color: OmiColors.textPrimary),
                keyboardType: TextInputType.url,
                autocorrect: false,
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return l10n.mcpServerUrl;
                  }
                  final uri = Uri.tryParse(value.trim());
                  if (uri == null || !uri.hasScheme || !uri.host.contains('.')) {
                    return l10n.mcpServerUrl;
                  }
                  return null;
                },
              ),
              const SizedBox(height: OmiSpacing.xxl),
              if (_isPolling) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const OmiSpinner(size: OmiSpinnerSize.small),
                    const SizedBox(width: OmiSpacing.xs),
                    Text(
                      l10n.authorizingMcpServer,
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.sm),
              ],
              OmiButton(
                label: l10n.connect,
                expand: true,
                isLoading: _isLoading,
                onPressed: (_isLoading || _isPolling) ? null : _connect,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
