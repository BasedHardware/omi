import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/google_calendar_service.dart';
import 'package:omi/services/notion_service.dart';
import 'package:omi/services/twitter_service.dart';
import 'package:omi/services/whoop_service.dart';
import 'package:provider/provider.dart';

enum IntegrationApp {
  googleCalendar,
  whoop,
  notion,
  twitter,
}

extension IntegrationAppExtension on IntegrationApp {
  String get displayName {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return 'Google';
      case IntegrationApp.whoop:
        return 'Whoop';
      case IntegrationApp.notion:
        return 'Notion';
      case IntegrationApp.twitter:
        return 'Twitter';
    }
  }

  String get key {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return 'google_calendar';
      case IntegrationApp.whoop:
        return 'whoop';
      case IntegrationApp.notion:
        return 'notion';
      case IntegrationApp.twitter:
        return 'twitter';
    }
  }

  String? get logoPath {
    switch (this) {
      case IntegrationApp.googleCalendar:
        // Use logo from assets - file is google-calendar.png
        // Direct path works even if not in generated assets file
        return 'assets/integration_app_logos/google-calendar.png';
      case IntegrationApp.whoop:
        // Use logo from assets - file is whoop.png
        // Direct path works even if not in generated assets file
        return 'assets/integration_app_logos/whoop.png';
      case IntegrationApp.notion:
        // Use logo from assets - file is notion-logo.png (if available)
        // Direct path works even if not in generated assets file
        return 'assets/integration_app_logos/notion-logo.png';
      case IntegrationApp.twitter:
        // Use logo from assets - file is twitter-logo.png (if available)
        // Direct path works even if not in generated assets file
        return 'assets/integration_app_logos/twitter-logo.png';
    }
  }

  IconData get icon {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return Icons.calendar_today;
      case IntegrationApp.whoop:
        return Icons.favorite; // Heart icon for health/fitness
      case IntegrationApp.notion:
        return Icons.note; // Note icon for Notion
      case IntegrationApp.twitter:
        return FontAwesomeIcons.twitter; // Twitter icon
    }
  }

  Color get iconColor {
    switch (this) {
      case IntegrationApp.googleCalendar:
        return const Color(0xFF4285F4);
      case IntegrationApp.whoop:
        return const Color(0xFF00D9FF); // Whoop brand color (cyan)
      case IntegrationApp.notion:
        return const Color(0xFF000000); // Notion brand color (black)
      case IntegrationApp.twitter:
        return const Color(0xFF1DA1F2); // Twitter brand color (blue)
    }
  }

  bool get isAvailable {
    return true; // All integrations are available
  }
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
    await context.read<IntegrationProvider>().loadFromBackend();
    // Also refresh the service's connection status
    await GoogleCalendarService().refreshConnectionStatus();
    await WhoopService().refreshConnectionStatus();
    await NotionService().refreshConnectionStatus();
    await TwitterService().refreshConnectionStatus();
  }

  Future<void> _connectApp(IntegrationApp app) async {
    if (!app.isAvailable) {
      return;
    }

    if (app == IntegrationApp.googleCalendar) {
      final service = GoogleCalendarService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) return;
    }

    if (app == IntegrationApp.whoop) {
      final service = WhoopService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) return;
    }

    if (app == IntegrationApp.notion) {
      final service = NotionService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) return;
    }

    if (app == IntegrationApp.twitter) {
      final service = TwitterService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) return;
    }
  }

  Future<bool> _handleAuthFlow(IntegrationApp app, bool isAuthenticated, Future<bool> Function() authenticate) async {
    if (isAuthenticated) return false;

    final shouldAuth = await _showAuthDialog(app);
    if (shouldAuth == true) {
      final success = await authenticate();
      if (success) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Please complete authentication in your browser. Once done, return to the app.'),
              duration: Duration(seconds: 5),
            ),
          );
        }
        await _loadFromBackend();
        debugPrint('✓ Integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to start ${app.displayName} authentication'),
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
            'Disconnect ${app.displayName}?',
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            'Are you sure you want to disconnect from ${app.displayName}? You can reconnect anytime.',
            style: const TextStyle(color: Color(0xFF8E8E93)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text(
                'Cancel',
                style: TextStyle(color: Color(0xFF8E8E93)),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text(
                'Disconnect',
                style: TextStyle(color: Colors.red),
              ),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {
      if (app == IntegrationApp.googleCalendar) {
        final googleCalendarService = GoogleCalendarService();
        final success = await googleCalendarService.disconnect();
        if (success) {
          await context.read<IntegrationProvider>().deleteConnection(app.key);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Disconnected from ${app.displayName}'),
                duration: const Duration(seconds: 2),
              ),
            );
          }
        } else {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Failed to disconnect'),
                backgroundColor: Colors.red,
                duration: Duration(seconds: 3),
              ),
            );
          }
        }
      } else if (app == IntegrationApp.whoop) {
        final whoopService = WhoopService();
        final success = await whoopService.disconnect();
        if (success) {
          await context.read<IntegrationProvider>().deleteConnection(app.key);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Disconnected from ${app.displayName}'),
                duration: const Duration(seconds: 2),
              ),
            );
          }
        } else {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Failed to disconnect'),
                backgroundColor: Colors.red,
                duration: Duration(seconds: 3),
              ),
            );
          }
        }
      } else if (app == IntegrationApp.notion) {
        final notionService = NotionService();
        final success = await notionService.disconnect();
        if (success) {
          await context.read<IntegrationProvider>().deleteConnection(app.key);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Disconnected from ${app.displayName}'),
                duration: const Duration(seconds: 2),
              ),
            );
          }
        } else {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Failed to disconnect'),
                backgroundColor: Colors.red,
                duration: Duration(seconds: 3),
              ),
            );
          }
        }
      } else if (app == IntegrationApp.twitter) {
        final twitterService = TwitterService();
        final success = await twitterService.disconnect();
        if (success) {
          await context.read<IntegrationProvider>().deleteConnection(app.key);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Disconnected from ${app.displayName}'),
                duration: const Duration(seconds: 2),
              ),
            );
          }
        } else {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Failed to disconnect'),
                backgroundColor: Colors.red,
                duration: Duration(seconds: 3),
              ),
            );
          }
        }
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
            'Connect to ${app.displayName}',
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            'You\'ll need to authorize Omi to access your ${app.displayName} data. This will open your browser for authentication.',
            style: const TextStyle(color: Color(0xFF8E8E93)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text(
                'Cancel',
                style: TextStyle(color: Color(0xFF8E8E93)),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text(
                'Continue',
                style: TextStyle(color: Colors.white),
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

  Widget _buildAppTile(IntegrationApp app) {
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    return GestureDetector(
      onTap: isAvailable
          ? () {
              if (isConnected) {
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
            // App Name and Status
            Expanded(
              child: Row(
                children: [
                  Text(
                    app.displayName,
                    style: TextStyle(
                      color: isAvailable ? Colors.white : Colors.grey,
                      fontSize: 17,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                  // Connected chip
                  if (isConnected) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.5),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Text(
                        'Linked',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            // Action Button
            if (!isConnected)
              // Connect button
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'Connect',
                  style: TextStyle(
                    color: Colors.black,
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
                child: const Text(
                  'Disconnect',
                  style: TextStyle(
                    color: Colors.red,
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

  @override
  Widget build(BuildContext context) {
    // Watch provider to rebuild when it changes
    context.watch<IntegrationProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Integrations',
          style: TextStyle(
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
                  children: IntegrationApp.values.map(_buildAppTile).toList(),
                ),
              ),
              const SizedBox(height: 16),

              // Footer Note
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.blue.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    FaIcon(
                      FontAwesomeIcons.puzzlePiece,
                      color: Colors.blue.withValues(alpha: 0.5),
                      size: 20,
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Text(
                        'Connect your apps to view data and metrics in chat.',
                        style: TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 14,
                          fontWeight: FontWeight.w400,
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
