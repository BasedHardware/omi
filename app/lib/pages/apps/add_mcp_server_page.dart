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
      this.authorizeServer = authorizeMcpServer,
      this.probeTimeout = const Duration(seconds: 20),
      this.waitTimeout = const Duration(minutes: 5)});
  final Future<Map<String, dynamic>?> Function(String, String, {String? description}) addServer;
  final Future<Map<String, dynamic>?> Function(String) appDetailsLoader;
  final Future<String?> Function(String appId) authorizeServer;
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
  ConnectionWait? _connectionWait;
  App? _readyApp;

  /// Registrations the server has already made, keyed by account and URL. Only an
  /// explicit Connect on that exact URL for that account reuses one; it is never the
  /// active state, so a late response for a retired attempt cannot touch the current one.
  final _registrations = <(String, String), _Registration>{};

  /// Per account and URL: the order registrations were requested in, and the newest
  /// one cached. A late reply for an older request never replaces a newer cached one.
  final _registrationRequests = <(String, String), int>{};
  final _cachedRequest = <(String, String), int>{};

  /// The one connect attempt allowed to act on this page. Each Connect press mints a
  /// new one; editing the URL, an account change or disposal retires it. Every await
  /// in an attempt rechecks [_owns] before it polls, navigates, shows an error or
  /// touches the loading state, so a retired attempt can never act for the URL the
  /// form shows now, and returning to its URL does not bring it back.
  _ConnectAttempt? _attempt;
  int _attemptGeneration = 0;

  _ConnectAttempt _beginAttempt(String url, String uid) => _attempt = _ConnectAttempt(++_attemptGeneration, url, uid);

  bool _owns(_ConnectAttempt attempt) =>
      mounted &&
      identical(_attempt, attempt) &&
      SharedPreferencesUtil().uid == attempt.uid &&
      _urlController.text.trim() == attempt.url;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _urlController.addListener(_serverChanged);
  }

  /// A registration and its authorization belong to the URL they were made for.
  /// Editing the URL away from the attempt's URL retires the whole attempt: its
  /// pending registration, browser launch, detail read and wait. The registration
  /// stays keyed to its own URL, so only an explicit Connect on that exact URL reuses it.
  void _serverChanged() {
    final attempt = _attempt;
    if (attempt == null || _urlController.text.trim() == attempt.url) return;
    _retireAttempt();
  }

  void _retireAttempt() {
    _attempt = null;
    _connectionWait?.cancel();
    _connectionWait = null;
    if (mounted && (_isPolling || _isLoading)) {
      setState(() {
        _isPolling = false;
        _isLoading = false;
      });
    }
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
    _attempt = null;
    _connectionWait?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _connect() async {
    if (_isLoading || _isPolling || !_formKey.currentState!.validate()) return;
    final uid = SharedPreferencesUtil().uid;
    // Own the submission before awaiting: everything that follows belongs to this
    // URL and account, not to whatever the field holds when a response arrives.
    final url = _urlController.text.trim();
    final attempt = _beginAttempt(url, uid);
    final cached = _registrations[(uid, url)];
    if (cached != null) {
      // An explicit retry on the URL the registration was made for reuses it. Its first
      // authorization state is single-use and expires, so the retry asks for a fresh one,
      // holding the button so a second press cannot rotate the authorization it is opening.
      setState(() => _isLoading = true);
      try {
        await _continueRegistration(attempt, cached, freshAuthorization: true);
      } finally {
        if (mounted && identical(_attempt, attempt)) setState(() => _isLoading = false);
      }
      return;
    }
    final key = (uid, url);
    final request = _registrationRequests[key] = (_registrationRequests[key] ?? 0) + 1;
    setState(() => _isLoading = true);
    try {
      final result = await widget
          .addServer(_nameController.text.trim(), url, description: _descriptionController.text.trim())
          .timeout(const Duration(seconds: 45));
      if (!mounted || SharedPreferencesUtil().uid != uid) return;
      if (result == null || result['error'] != null) {
        if (_owns(attempt)) {
          _showError(result?['error'] is String ? result!['error'] as String : context.l10n.mcpConnectionFailed);
        }
        return;
      }
      final id = result['app_id'];
      if (id is! String || id.isEmpty || result['requires_oauth'] is! bool) {
        if (mounted && _owns(attempt)) _showError(context.l10n.mcpConnectionFailed);
        return;
      }
      // The server registered this URL for this account even if the attempt was
      // retired meanwhile; cache it under that account and URL for an explicit retry,
      // without touching whichever attempt is active now.
      final authUrl = result['auth_url'];
      final registration = _Registration(id, result['requires_oauth'] == true, authUrl is String ? authUrl : null);
      if (request > (_cachedRequest[key] ?? 0)) {
        _registrations[key] = registration;
        _cachedRequest[key] = request;
      }
      if (!_owns(attempt)) return;
      await _continueRegistration(attempt, registration);
    } catch (_) {
      if (mounted && _owns(attempt)) _showError(context.l10n.mcpConnectionFailed);
    } finally {
      // A retired attempt already released the button, and a newer one owns it now;
      // the current attempt releases it even when its account has changed.
      if (mounted && identical(_attempt, attempt)) setState(() => _isLoading = false);
    }
  }

  Future<void> _continueRegistration(_ConnectAttempt attempt, _Registration registration,
      {bool freshAuthorization = false}) async {
    if (!registration.requiresOAuth) {
      await _navigateToAppDetail(registration.appId, attempt);
      return;
    }
    String? authUrl = registration.authUrl;
    if (freshAuthorization) {
      try {
        // The same bound as registration: authorization is a server-side mutation, so a short
        // probe deadline would release the button while it can still rotate the verifier.
        authUrl = await widget.authorizeServer(registration.appId).timeout(const Duration(seconds: 45));
      } catch (_) {
        authUrl = null;
      }
    }
    if (!_owns(attempt)) return;
    if (authUrl == null || !await launchIntegrationOAuth(() async => authUrl, isCurrent: () => _owns(attempt))) {
      if (mounted && _owns(attempt)) _showError(context.l10n.mcpConnectionFailed);
      return;
    }
    if (_owns(attempt)) _startPollingForCompletion(attempt, registration.appId);
  }

  void _startPollingForCompletion(_ConnectAttempt attempt, String id) {
    if (!_owns(attempt)) return;
    _connectionWait?.cancel();
    _readyApp = null;
    setState(() => _isPolling = true);
    late final ConnectionWait wait;
    wait = ConnectionWait(
      isCurrent: () => _owns(attempt),
      probeTimeout: widget.probeTimeout,
      waitTimeout: widget.waitTimeout,
      probe: () async {
        final data = await widget.appDetailsLoader(id);
        if (!wait.isActive || !_owns(attempt)) {
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
      if (!_owns(attempt)) return;
      if (outcome == ConnectionWaitOutcome.connected && _readyApp != null) {
        _showConnectedApp(_readyApp!);
      } else if (outcome != ConnectionWaitOutcome.cancelled) {
        _showError(context.l10n.mcpConnectionFailed);
      }
    }));
  }

  Future<void> _navigateToAppDetail(String id, _ConnectAttempt attempt) async {
    final data = await widget.appDetailsLoader(id).timeout(widget.probeTimeout);
    if (!mounted || !_owns(attempt)) return;
    if (data == null) {
      _showError(context.l10n.mcpConnectionFailed);
      return;
    }
    final app = App.fromJson(data);
    if (app.id != id || app.status != 'approved') {
      _showError(context.l10n.mcpConnectionFailed);
      return;
    }
    // A server without OAuth is registered approved but not enabled: its detail page
    // owns the Enable action. Only a server-confirmed enabled app is announced as connected.
    _showConnectedApp(app, announce: app.enabled);
  }

  void _showConnectedApp(App app, {bool announce = true}) {
    if (!mounted || ModalRoute.of(context)?.isCurrent != true) return;
    if (announce) OmiFeedback.confirm(context, context.l10n.mcpServerConnected(app.chatTools?.length ?? 0));
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
                // The page owns loading and attempt state; editing the URL retires a pending
                // attempt, so the button must not stay locked on that attempt's future.
                onPressed: (_isLoading || _isPolling) ? null : () => unawaited(_connect()),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A server registration, fixed to the account and URL it was made for.
class _Registration {
  const _Registration(this.appId, this.requiresOAuth, this.authUrl);
  final String appId;
  final bool requiresOAuth;
  final String? authUrl;
}

/// One Connect press: the URL and account it was made for, and its place in order.
class _ConnectAttempt {
  _ConnectAttempt(this.generation, this.url, this.uid);
  final int generation;
  final String url;
  final String uid;
}
