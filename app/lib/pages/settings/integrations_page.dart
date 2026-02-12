import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/apple_health_service.dart';
import 'package:omi/services/google_calendar_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';

enum IntegrationApp {
  appleHealth,
  googleCalendar,
  gmail,
}

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
        return const Color(0xFF4285F4);
      case IntegrationApp.gmail:
        return const Color(0xFFEA4335);
      case IntegrationApp.appleHealth:
        return const Color(0xFFFF2D55); // Apple Health brand color (pink/red)
    }
  }

  bool get isAvailable {
    if (this == IntegrationApp.gmail) return false;
    // Apple Health is only available on iOS/macOS
    if (this == IntegrationApp.appleHealth) {
      return true; // Will check platform availability at runtime in the service
    }
    return true;
  }

  // String get comingSoonText {
  //   return 'Coming Soon';
  // }
}

class IntegrationsPage extends StatefulWidget {
  const IntegrationsPage({super.key});

  @override
  State<IntegrationsPage> createState() => _IntegrationsPageState();
}

class _IntegrationsPageState extends State<IntegrationsPage> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    MixpanelManager().integrationsPageOpened();
    WidgetsBinding.instance.addObserver(this);
    // Schedule loading for after the first frame to avoid setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadFromBackend();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh when app comes back from background (e.g., after OAuth)
      _loadFromBackend();
    }
  }

  Future<void> _loadFromBackend() async {
    // IntegrationProvider.loadFromBackend() already fetches all connection statuses
    // and syncs SharedPreferences for backward compatibility with services
    await context.read<IntegrationProvider>().loadFromBackend();
  }

  Future<void> _connectApp(IntegrationApp app) async {
    if (!app.isAvailable) {
      return;
    }
    MixpanelManager().integrationConnectAttempted(integrationName: app.displayName);

    if (app == IntegrationApp.googleCalendar) {
      final service = GoogleCalendarService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) return;
    }

    if (app == IntegrationApp.appleHealth) {
      await _handleAppleHealthConnect();
      return;
    }
  }

  Future<void> _handleAppleHealthConnect() async {
    final service = AppleHealthService();

    if (!service.isAvailable) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.appleHealthNotAvailable),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
      return;
    }

    final shouldAuth = await _showAuthDialog(IntegrationApp.appleHealth);
    if (shouldAuth == true) {
      if (!mounted) return;
      final scaffoldMessenger = ScaffoldMessenger.of(context);
      final integrationProvider = context.read<IntegrationProvider>();

      final result = await service.connect();
      if (result.isSuccess) {
        MixpanelManager().integrationConnectSucceeded(integrationName: 'Apple Health');
        // Sync health data to the backend
        final synced = await service.syncHealthDataToBackend(days: 7);
        if (synced) {
          Logger.debug('✓ Apple Health data synced to backend');
        } else {
          Logger.debug('⚠ Failed to sync Apple Health data, but connection succeeded');
        }

        // Save the connection status to the backend (this is a fallback in case sync partially failed)
        await integrationProvider.saveConnection(IntegrationApp.appleHealth.key, {});
        if (mounted) {
          scaffoldMessenger.showSnackBar(
            SnackBar(
              content: Text(result.message),
              duration: const Duration(seconds: 2),
            ),
          );
        }
        await _loadFromBackend();
      } else {
        MixpanelManager().integrationConnectFailed(integrationName: 'Apple Health');
        if (mounted) {
          scaffoldMessenger.showSnackBar(
            SnackBar(
              content: Text(result.message),
              backgroundColor: Colors.red,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      }
    }
  }

  Future<bool> _handleAuthFlow(IntegrationApp app, bool isAuthenticated, Future<bool> Function() authenticate) async {
    if (isAuthenticated) return false;

    final shouldAuth = await _showAuthDialog(app);
    if (shouldAuth == true) {
      // Capture ScaffoldMessenger before async operation to avoid use_build_context_synchronously
      if (!mounted) return false;
      final scaffoldMessenger = ScaffoldMessenger.of(context);

      final success = await authenticate();
      if (success) {
        MixpanelManager().integrationConnectSucceeded(integrationName: app.displayName);
        if (mounted) {
          scaffoldMessenger.showSnackBar(
            SnackBar(
              content: Text(context.l10n.completeAuthInBrowser),
              duration: const Duration(seconds: 5),
            ),
          );
        }
        await _loadFromBackend();
        Logger.debug('✓ Integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
      } else {
        MixpanelManager().integrationConnectFailed(integrationName: app.displayName);
        if (mounted) {
          scaffoldMessenger.showSnackBar(
            SnackBar(
              content: Text(context.l10n.failedToStartAuth(app.displayName)),
              backgroundColor: Colors.red,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      }
    }
    return true;
  }

  Future<void> _disconnectApp(IntegrationApp app) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            context.l10n.disconnectAppTitle(app.displayName),
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            context.l10n.disconnectAppMessage(app.displayName),
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
      if (app == IntegrationApp.googleCalendar) {
        final service = GoogleCalendarService();
        await _handleDisconnect(app, service.disconnect);
      } else if (app == IntegrationApp.appleHealth) {
        // Capture instances before async operation to avoid use_build_context_synchronously
        if (!mounted) return;
        final integrationProvider = context.read<IntegrationProvider>();
        final scaffoldMessenger = ScaffoldMessenger.of(context);

        final success = await integrationProvider.deleteConnection(IntegrationApp.appleHealth.key);
        if (success) {
          MixpanelManager().integrationDisconnected(integrationName: 'Apple Health');
          if (mounted) {
            scaffoldMessenger.showSnackBar(
              SnackBar(
                content: Text(context.l10n.disconnectedFrom(IntegrationApp.appleHealth.displayName)),
                duration: const Duration(seconds: 2),
              ),
            );
          }
        } else {
          if (mounted) {
            scaffoldMessenger.showSnackBar(
              SnackBar(
                content: Text(context.l10n.failedToDisconnect),
                backgroundColor: Colors.red,
                duration: const Duration(seconds: 3),
              ),
            );
          }
        }
      }
    }
  }

  Future<void> _handleDisconnect(IntegrationApp app, Future<bool> Function() disconnect) async {
    // Capture instances before async operation to avoid use_build_context_synchronously
    final integrationProvider = context.read<IntegrationProvider>();
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final success = await disconnect();
    if (success) {
      MixpanelManager().integrationDisconnected(integrationName: app.displayName);
      if (mounted) {
        await integrationProvider.deleteConnection(app.key);
      }
      if (mounted) {
        scaffoldMessenger.showSnackBar(
          SnackBar(
            content: Text(context.l10n.disconnectedFrom(app.displayName)),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } else {
      if (mounted) {
        scaffoldMessenger.showSnackBar(
          SnackBar(
            content: Text(context.l10n.failedToDisconnect),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  Future<bool?> _showAuthDialog(IntegrationApp app) {
    return showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            context.l10n.connectTo(app.displayName),
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            context.l10n.authAccessMessage(app.displayName),
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
                context.l10n.continueAction,
                style: const TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );
  }

  bool _isAppConnected(IntegrationApp app) {
    // Use provider to get connection status so it updates reactively
    return context.read<IntegrationProvider>().isAppConnected(app);
  }

  Widget _buildShimmerButton() {
    return ShimmerWithTimeout(
      baseColor: Colors.grey.shade800,
      highlightColor: Colors.grey.shade600,
      child: Container(
        width: 80,
        height: 32,
        decoration: BoxDecoration(
          color: Colors.grey.shade800,
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    );
  }

  Widget _buildAppTile(IntegrationApp app, bool isLoading) {
    final isConnected = _isAppConnected(app);
    final isAvailable = app.isAvailable;

    return GestureDetector(
      onTap: isAvailable
          ? () {
              if (isLoading) return;

              if (isConnected) {
                // Show disconnect dialog
                _disconnectApp(app);
              } else {
                _connectApp(app);
              }
            }
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
        child: Row(
          children: [
            // App Icon/Logo
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
              ),
              child: app.logoPath != null
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.asset(
                        app.logoPath!,
                        width: 40,
                        height: 40,
                        fit: BoxFit.contain,
                        errorBuilder: (context, error, stackTrace) {
                          return Container(
                            decoration: BoxDecoration(
                              color: isAvailable ? app.iconColor.withOpacity(0.2) : Colors.grey.withOpacity(0.1),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              app.icon,
                              color: isAvailable ? app.iconColor : Colors.grey,
                              size: 24,
                            ),
                          );
                        },
                      ),
                    )
                  : Container(
                      decoration: BoxDecoration(
                        color: isAvailable ? app.iconColor.withOpacity(0.2) : Colors.grey.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(
                        app.icon,
                        color: isAvailable ? app.iconColor : Colors.grey,
                        size: 24,
                      ),
                    ),
            ),
            const SizedBox(width: 16),
            // App Name
            Expanded(
              child: Text(
                app.displayName,
                style: TextStyle(
                  color: isAvailable ? Colors.white : Colors.grey,
                  fontSize: 17,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            // Action Button - Show shimmer while loading
            if (isLoading)
              _buildShimmerButton()
            else if (!isConnected)
              // Connect button
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: !isAvailable ? Colors.grey.withValues(alpha: 0.3) : Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  !isAvailable ? context.l10n.comingSoon : context.l10n.connect,
                  style: TextStyle(
                    color: !isAvailable ? Colors.grey : Colors.black,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              )
            else
              // Disconnect button
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  context.l10n.disconnect,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildCreateYourOwnAppTile() {
    return GestureDetector(
      onTap: () {
        routeToPage(
          context,
          const AddAppPage(presetExternalIntegration: true),
        );
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
        child: Row(
          children: [
            // Icon
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: Colors.purple.withOpacity(0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.add_circle_outline,
                color: Colors.purple,
                size: 24,
              ),
            ),
            const SizedBox(width: 16),
            // App Name
            Expanded(
              child: Text(
                context.l10n.createYourOwnApp,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
            // Arrow icon
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.purple.withOpacity(0.2),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Icon(
                Icons.arrow_forward_ios,
                color: Colors.purple,
                size: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Watch provider to rebuild when it changes
    final provider = context.watch<IntegrationProvider>();
    final isLoading = provider.isLoading || !provider.hasLoaded;

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
          context.l10n.integrations,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // App List
              Expanded(
                child: ListView(
                  children: [
                    ...IntegrationApp.values.map((app) => _buildAppTile(app, isLoading)),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Divider(
                        color: Colors.grey.shade800,
                        thickness: 1,
                      ),
                    ),
                    _buildCreateYourOwnAppTile(),
                  ],
                ),
              ),
              // Footer
              Padding(
                padding: const EdgeInsets.only(top: 20),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, color: Color(0xFF8E8E93), size: 16),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        context.l10n.integrationsFooter,
                        style: const TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 12,
                        ),
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
