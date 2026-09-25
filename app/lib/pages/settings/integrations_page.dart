import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/settings/apple_health_detail_page.dart';
import 'package:omi/pages/settings/integration_selection_card.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/integrations/apple_health_service.dart';
import 'package:omi/services/integrations/gmail_service.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

enum IntegrationApp { appleHealth, googleCalendar, gmail }

enum _IntegrationAuthOutcome { alreadyAuthenticated, cancelled, started, failed }

extension IntegrationAppExtension on IntegrationApp {
  String get displayName {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return 'Google Calendar';
      case IntegrationApp.gmail:
        return 'Gmail';
      case IntegrationApp.appleHealth:
        return 'Apple Health';
    }
  }

  /// Name shown in the disconnect confirmation. Gmail and Google Calendar share a
  /// single Google grant, so disconnecting either one drops both.
  String get disconnectDisplayName {
    switch (this) {
      case IntegrationApp.gmail:
      case IntegrationApp.googleCalendar:
        return 'Gmail and Google Calendar';
      case IntegrationApp.appleHealth:
        return displayName;
    }
  }

  String get key {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return 'google_calendar';
      case IntegrationApp.gmail:
        return 'gmail';
      case IntegrationApp.appleHealth:
        return 'apple_health';
    }
  }

  String? get logoPath {
    switch (this) {
      case IntegrationApp.googleCalendar:
        // Use logo from assets - file is google-calendar.png
        // Direct path works even if not in generated assets file
        return 'assets/integration_app_logos/google-calendar.png';
      case IntegrationApp.gmail:
        return 'assets/integration_app_logos/gmail-logo.jpeg';
      case IntegrationApp.appleHealth:
        // Use logo from assets - file is apple-health-logo.png
        return 'assets/integration_app_logos/apple-health-logo.png';
    }
  }

  IconData get icon {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return Icons.calendar_today;
      case IntegrationApp.gmail:
        return Icons.mail;
      case IntegrationApp.appleHealth:
        return Icons.favorite; // Heart icon for health
    }
  }

  Color get iconColor {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return const Color(0xFF4285F4); // omi-ux-allow: color-literal -- third-party brand colour
      case IntegrationApp.gmail:
        return const Color(0xFFEA4335); // omi-ux-allow: color-literal -- third-party brand colour
      case IntegrationApp.appleHealth:
        return const Color(0xFFFF2D55); // omi-ux-allow: color-literal -- third-party brand colour
    }
  }

  bool get isAvailable {
    // Apple Health checks platform availability at runtime in the service.
    return true;
  }
}

class IntegrationsPage extends StatefulWidget {
  const IntegrationsPage({super.key});

  @override
  State<IntegrationsPage> createState() => _IntegrationsPageState();
}

class _IntegrationsPageState extends State<IntegrationsPage> with WidgetsBindingObserver {
  final Map<IntegrationApp, ProductAttempt> _pendingIntegrationAttempts = {};

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.integrationsPageOpened();
    WidgetsBinding.instance.addObserver(this);
    // Schedule loading for after the first frame to avoid setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadFromBackend();
    });
  }

  @override
  void dispose() {
    for (final attempt in _pendingIntegrationAttempts.values) {
      attempt.complete(ProductOutcome.unobserved, failure: ProductFailure.incomplete);
    }
    _pendingIntegrationAttempts.clear();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh when app comes back from background (e.g., after OAuth)
      _loadFromBackend().then((_) => _resolvePendingIntegrationAttempts());
    }
  }

  Future<void> _loadFromBackend() async {
    // IntegrationProvider.loadFromBackend() already fetches all connection statuses
    // and syncs SharedPreferences for backward compatibility with services
    await context.read<IntegrationProvider>().loadFromBackend();
    _resolvePendingIntegrationAttempts();
  }

  void _resolvePendingIntegrationAttempts() {
    if (!mounted || _pendingIntegrationAttempts.isEmpty) return;
    final provider = context.read<IntegrationProvider>();
    for (final entry in Map<IntegrationApp, ProductAttempt>.from(_pendingIntegrationAttempts).entries) {
      if (provider.isAppConnected(entry.key)) {
        entry.value.complete(ProductOutcome.success);
        _pendingIntegrationAttempts.remove(entry.key);
      }
    }
  }

  Future<void> _connectApp(IntegrationApp app) async {
    if (!app.isAvailable) {
      return;
    }
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.integrationConnect,
      surface: ProductSurface.integration,
    );
    PlatformManager.instance.analytics.integrationConnectAttempted(integrationName: app.displayName);

    if (app == IntegrationApp.googleCalendar) {
      final service = GoogleCalendarService();
      final outcome = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      _completeIntegrationAttempt(attempt, app, outcome);
      return;
    }

    if (app == IntegrationApp.gmail) {
      final service = GmailService();
      final outcome = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      _completeIntegrationAttempt(attempt, app, outcome);
      return;
    }

    if (app == IntegrationApp.appleHealth) {
      await _openAppleHealthDetail();
      if (mounted && context.read<IntegrationProvider>().isAppConnected(app)) {
        attempt.complete(ProductOutcome.success);
      } else {
        attempt.complete(ProductOutcome.failure, failure: ProductFailure.permissionDenied);
      }
      return;
    }
    attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
  }

  void _completeIntegrationAttempt(ProductAttempt attempt, IntegrationApp app, _IntegrationAuthOutcome outcome) {
    switch (outcome) {
      case _IntegrationAuthOutcome.alreadyAuthenticated:
        attempt.complete(ProductOutcome.success);
      case _IntegrationAuthOutcome.started:
        if (mounted && context.read<IntegrationProvider>().isAppConnected(app)) {
          attempt.complete(ProductOutcome.success);
        } else {
          // OAuth has handed off to the browser. Keep this attempt open until
          // the returning app observes the persisted connection state.
          _pendingIntegrationAttempts.remove(app)?.complete(ProductOutcome.superseded);
          _pendingIntegrationAttempts[app] = attempt;
        }
      case _IntegrationAuthOutcome.cancelled:
        attempt.complete(ProductOutcome.cancelled);
      case _IntegrationAuthOutcome.failed:
        attempt.complete(ProductOutcome.failure, failure: ProductFailure.network);
    }
  }

  Future<void> _openAppleHealthDetail() async {
    if (!AppleHealthService().isAvailable) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.appleHealthNotAvailable);
      }
      return;
    }
    await routeToPage(context, const AppleHealthDetailPage());
    if (mounted) await _loadFromBackend();
  }

  Future<_IntegrationAuthOutcome> _handleAuthFlow(
    IntegrationApp app,
    bool isAuthenticated,
    Future<bool> Function() authenticate,
  ) async {
    if (isAuthenticated) return _IntegrationAuthOutcome.alreadyAuthenticated;

    final shouldAuth = await _showAuthDialog(app);
    if (!shouldAuth) return _IntegrationAuthOutcome.cancelled;
    if (!mounted) return _IntegrationAuthOutcome.failed;

    final success = await authenticate();
    if (success) {
      PlatformManager.instance.analytics.integrationConnectSucceeded(integrationName: app.displayName);
      if (mounted) OmiFeedback.info(context, context.l10n.completeAuthInBrowser);
      await _loadFromBackend();
      Logger.debug('✓ Integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
      return _IntegrationAuthOutcome.started;
    } else {
      PlatformManager.instance.analytics.integrationConnectFailed(integrationName: app.displayName);
      if (mounted) OmiFeedback.error(context, context.l10n.failedToStartAuth(app.displayName));
      return _IntegrationAuthOutcome.failed;
    }
  }

  Future<void> _disconnectApp(IntegrationApp app) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.disconnectAppTitle(app.disconnectDisplayName),
      message: context.l10n.disconnectAppMessage(app.disconnectDisplayName),
      confirmLabel: context.l10n.disconnect,
      destructive: true,
    );
    if (!confirmed || !mounted) return;

    if (app == IntegrationApp.googleCalendar) {
      await _handleDisconnect(app, GoogleCalendarService().disconnect);
    } else if (app == IntegrationApp.gmail) {
      await _handleDisconnect(app, GmailService().disconnect);
    } else if (app == IntegrationApp.appleHealth) {
      final success = await context.read<IntegrationProvider>().deleteConnection(IntegrationApp.appleHealth.key);
      if (success) PlatformManager.instance.analytics.integrationDisconnected(integrationName: 'Apple Health');
      if (!mounted) return;
      if (success) {
        OmiFeedback.confirm(context, context.l10n.disconnectedFrom(IntegrationApp.appleHealth.displayName));
      } else {
        OmiFeedback.error(context, context.l10n.failedToDisconnect);
      }
    }
  }

  Future<void> _handleDisconnect(IntegrationApp app, Future<bool> Function() disconnect) async {
    // Capture the provider before the async gap to avoid use_build_context_synchronously
    final integrationProvider = context.read<IntegrationProvider>();

    final success = await disconnect();
    if (success) {
      PlatformManager.instance.analytics.integrationDisconnected(integrationName: app.displayName);
      // Re-read every row: Gmail and Google Calendar share one grant, so dropping
      // either one also disconnects the other.
      if (mounted) {
        await integrationProvider.loadFromBackend();
      }
      if (mounted) OmiFeedback.confirm(context, context.l10n.disconnectedFrom(app.displayName));
    } else {
      if (mounted) OmiFeedback.error(context, context.l10n.failedToDisconnect);
    }
  }

  Future<bool> _showAuthDialog(IntegrationApp app) {
    return showOmiConfirm(
      context,
      title: context.l10n.connectTo(app.displayName),
      message: context.l10n.authAccessMessage(app.displayName),
      confirmLabel: context.l10n.continueAction,
    );
  }

  bool _isAppConnected(IntegrationApp app) {
    // Use provider to get connection status so it updates reactively
    return context.read<IntegrationProvider>().isAppConnected(app);
  }

  Widget _buildShimmerButton() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface3,
      child: Container(
        width: 80,
        height: 32,
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
      ),
    );
  }

  Widget _fallbackIcon(IntegrationApp app, bool isAvailable) {
    return Container(
      decoration: BoxDecoration(
        color: isAvailable ? app.iconColor.withValues(alpha: 0.2) : OmiColors.surface2,
        borderRadius: OmiRadius.smAll,
      ),
      child: Icon(app.icon, color: isAvailable ? app.iconColor : OmiColors.textTertiary, size: 24),
    );
  }

  /// One tappable row: the whole row is the button, announced with its trailing action.
  Widget _buildRow({required Widget leading, required String title, required Widget trailing, VoidCallback? onTap}) {
    return MergeSemantics(
      child: Semantics(
        button: true,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: OmiSpacing.md),
            child: Row(
              children: [
                ExcludeSemantics(child: SizedBox(width: 40, height: 40, child: leading)),
                const SizedBox(width: OmiSpacing.md),
                Expanded(child: Text(title, style: OmiType.body)),
                trailing,
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAppTile(IntegrationApp app, bool isLoading) {
    final isConnected = _isAppConnected(app);
    final isAvailable = app.isAvailable;

    final Widget trailing;
    if (isLoading) {
      trailing = _buildShimmerButton();
    } else if (!isAvailable) {
      trailing = IntegrationStatusChip(context.l10n.comingSoon, tone: IntegrationChipTone.muted);
    } else if (!isConnected) {
      trailing = IntegrationStatusChip(context.l10n.connect);
    } else {
      trailing = IntegrationStatusChip(context.l10n.disconnect, tone: IntegrationChipTone.danger);
    }

    return _buildRow(
      leading: app.logoPath != null
          ? ClipRRect(
              borderRadius: OmiRadius.smAll,
              child: Image.asset(
                app.logoPath!,
                width: 40,
                height: 40,
                fit: BoxFit.contain,
                errorBuilder: (context, error, stackTrace) => _fallbackIcon(app, isAvailable),
              ),
            )
          : _fallbackIcon(app, isAvailable),
      title: app.displayName,
      trailing: trailing,
      onTap: isAvailable
          ? () {
              if (isLoading) return;

              if (app == IntegrationApp.appleHealth) {
                _openAppleHealthDetail();
                return;
              }

              if (isConnected) {
                // Show disconnect dialog
                _disconnectApp(app);
              } else {
                _connectApp(app);
              }
            }
          : null,
    );
  }

  Widget _buildCreateYourOwnAppTile() {
    return _buildRow(
      leading: Container(
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
        child: const Icon(Icons.add_circle_outline, color: OmiColors.textPrimary, size: 24),
      ),
      title: context.l10n.createYourOwnApp,
      trailing: const Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 20),
      onTap: () => routeToPage(context, const AddAppPage(presetExternalIntegration: true)),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Watch provider to rebuild when it changes
    final provider = context.watch<IntegrationProvider>();
    final isLoading = provider.isLoading || !provider.hasLoaded;

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.integrations)),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // App List
              Expanded(
                child: ListView(
                  children: [
                    ...IntegrationApp.values.map((app) => _buildAppTile(app, isLoading)),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: OmiSpacing.xs),
                      child: Divider(color: OmiColors.border, thickness: 1),
                    ),
                    _buildCreateYourOwnAppTile(),
                  ],
                ),
              ),
              // Footer
              Padding(
                padding: const EdgeInsets.only(top: OmiSpacing.lg),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, color: OmiColors.textTertiary, size: 16),
                    const SizedBox(width: OmiSpacing.xs),
                    Expanded(
                      child: Text(
                        context.l10n.integrationsFooter,
                        style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
