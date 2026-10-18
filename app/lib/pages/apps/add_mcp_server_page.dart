import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/integrations/connection_wait.dart';
import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'widgets/app_form_fields.dart';

class AddMcpServerPage extends StatefulWidget {
  const AddMcpServerPage(
      {super.key,
      this.addServer = addMcpServer,
      this.appDetailsLoader = getAppDetailsServer,
      this.probeTimeout = const Duration(seconds: 20),
      this.waitTimeout = const Duration(minutes: 5)});
  final Future<Map<String, dynamic>?> Function(String, String, {String? description}) addServer;
  final Future<Map<String, dynamic>?> Function(String) appDetailsLoader;
  final Duration probeTimeout;
  final Duration waitTimeout;

  @override
  State<AddMcpServerPage> createState() => _AddMcpServerPageState();
}

class _AddMcpServerPageState extends State<AddMcpServerPage> with WidgetsBindingObserver {
  final _nameController = TextEditingController();
  final _urlController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  bool _isLoading = false;
  bool _isPolling = false;
  String? _appId;
  ConnectionWait? _connectionWait;
  App? _readyApp;
  String? _submittedUrl;
  String? _authUrl;
  String? _submittedUid;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _urlController.addListener(_serverChanged);
  }

  /// A registration and its authorization belong to the URL they were made for.
  /// Editing the URL away from it stops waiting on that server; the registration
  /// stays keyed to its own URL, so only returning to that exact URL reuses it.
  void _serverChanged() {
    final submitted = _submittedUrl;
    if (submitted == null || _urlController.text.trim() == submitted) return;
    if (_connectionWait == null && !_isPolling) return;
    _connectionWait?.cancel();
    _connectionWait = null;
    if (_isPolling && mounted) setState(() => _isPolling = false);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _connectionWait?.refresh();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    _descriptionController.dispose();
    _connectionWait?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _connect() async {
    if (_isLoading || _isPolling || !_formKey.currentState!.validate()) return;
    final uid = SharedPreferencesUtil().uid;
    if (_submittedUid != null && _submittedUid != SharedPreferencesUtil().uid) {
      _connectionWait?.cancel();
      _appId = null;
      _authUrl = null;
      _submittedUrl = null;
    }
    if (_appId != null && _submittedUrl == _urlController.text.trim()) {
      if (_authUrl != null &&
          !await launchIntegrationOAuth(() async => _authUrl,
              isCurrent: () => mounted && SharedPreferencesUtil().uid == uid)) {
        if (mounted && SharedPreferencesUtil().uid == uid) _showError(context.l10n.mcpConnectionFailed);
        return;
      }
      if (mounted && SharedPreferencesUtil().uid == uid) _startPollingForCompletion();
      return;
    }
    // Own the submission before awaiting: the response belongs to this URL, not
    // to whatever the field holds when it arrives.
    final url = _urlController.text.trim();
    setState(() => _isLoading = true);
    try {
      final result = await widget
          .addServer(_nameController.text.trim(), url, description: _descriptionController.text.trim())
          .timeout(const Duration(seconds: 45));
      if (!mounted || SharedPreferencesUtil().uid != uid) return;
      if (result == null || result['error'] != null) {
        _showError(result?['error'] is String ? result!['error'] as String : context.l10n.mcpConnectionFailed);
        return;
      }
      final id = result['app_id'];
      if (id is! String || id.isEmpty || result['requires_oauth'] is! bool) {
        _showError(context.l10n.mcpConnectionFailed);
        return;
      }
      _appId = id;
      _submittedUrl = url;
      _submittedUid = uid;
      final authUrl = result['auth_url'];
      _authUrl = result['requires_oauth'] == true && authUrl is String ? authUrl : null;
      // The user moved on to another server while this one registered.
      if (_urlController.text.trim() != url) return;
      if (result['requires_oauth'] == true) {
        if (authUrl is! String ||
            !await launchIntegrationOAuth(() async => authUrl,
                isCurrent: () => mounted && SharedPreferencesUtil().uid == uid)) {
          if (mounted) _showError(context.l10n.mcpConnectionFailed);
          return;
        }
        if (mounted && SharedPreferencesUtil().uid == uid) _startPollingForCompletion();
      } else {
        await _navigateToAppDetail(id, uid);
      }
    } catch (_) {
      if (mounted && SharedPreferencesUtil().uid == uid) _showError(context.l10n.mcpConnectionFailed);
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _startPollingForCompletion() {
    final id = _appId;
    if (id == null || !mounted) return;
    _connectionWait?.cancel();
    _readyApp = null;
    final uid = SharedPreferencesUtil().uid;
    setState(() => _isPolling = true);
    late final ConnectionWait wait;
    wait = ConnectionWait(
      isCurrent: () => mounted && _appId == id && SharedPreferencesUtil().uid == uid,
      probeTimeout: widget.probeTimeout,
      waitTimeout: widget.waitTimeout,
      probe: () async {
        final data = await widget.appDetailsLoader(id);
        if (!mounted || !wait.isActive || _appId != id || SharedPreferencesUtil().uid != uid) {
          return ConnectionProbe.pending;
        }
        if (data == null) return ConnectionProbe.failed;
        if (data['status'] == 'approved') {
          final app = App.fromJson(data);
          if (app.id != id) return ConnectionProbe.failed;
          if (!app.enabled) return ConnectionProbe.pending;
          _readyApp = app;
          return ConnectionProbe.connected;
        }
        if (['failed', 'rejected', 'disabled'].contains(data['status'])) return ConnectionProbe.failed;
        return ConnectionProbe.pending;
      },
    );
    _connectionWait = wait;
    unawaited(wait.start().then((outcome) {
      if (!mounted || !identical(_connectionWait, wait)) return;
      setState(() => _isPolling = false);
      if (outcome == ConnectionWaitOutcome.connected && _readyApp != null) {
        _showConnectedApp(_readyApp!);
      } else if (outcome != ConnectionWaitOutcome.cancelled) {
        _showError(context.l10n.mcpConnectionFailed);
      }
    }));
  }

  Future<void> _navigateToAppDetail(String id, String uid) async {
    final data = await widget.appDetailsLoader(id).timeout(widget.probeTimeout);
    if (!mounted || SharedPreferencesUtil().uid != uid) return;
    if (data == null) {
      _showError(context.l10n.mcpConnectionFailed);
      return;
    }
    final app = App.fromJson(data);
    if (app.id != id || app.status != 'approved' || !app.enabled) {
      _showError(context.l10n.mcpConnectionFailed);
      return;
    }
    _showConnectedApp(app);
  }

  void _showConnectedApp(App app) {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return;
    OmiFeedback.confirm(context, context.l10n.mcpServerConnected(app.chatTools?.length ?? 0));
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(builder: (_) => AppDetailPage(app: app)));
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
              Text(l10n.connectExternalAiTools, style: OmiType.body.copyWith(color: OmiColors.textSecondary)),
              const SizedBox(height: OmiSpacing.xxl),
              TextFormField(
                controller: _nameController,
                decoration: appFormInputDecoration(label: l10n.appName, hint: 'e.g. Mixpanel Analytics'),
                style: TextStyle(color: OmiColors.textPrimary),
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
                decoration: appFormInputDecoration(label: l10n.descriptionOptional).copyWith(hintMaxLines: 1),
                style: TextStyle(color: OmiColors.textPrimary),
                minLines: 1,
                maxLines: 2,
              ),
              const SizedBox(height: OmiSpacing.md),
              TextFormField(
                controller: _urlController,
                decoration: appFormInputDecoration(label: l10n.mcpServerUrl, hint: 'https://mcp.example.com/mcp'),
                style: TextStyle(color: OmiColors.textPrimary),
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
                    Text(l10n.authorizingMcpServer, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
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
