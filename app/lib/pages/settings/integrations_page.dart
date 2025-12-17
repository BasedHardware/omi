import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/google_calendar_service.dart';
import 'package:omi/services/notion_service.dart';
import 'package:omi/services/twitter_service.dart';
import 'package:omi/services/whoop_service.dart';
import 'package:omi/services/github_service.dart';
import 'package:omi/pages/settings/github_settings_page.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

enum IntegrationApp {
  whoop,
  notion,
  twitter,
  github,
  googleCalendar,
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
      case IntegrationApp.github:
        return 'GitHub';
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
      case IntegrationApp.github:
        return 'github';
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
        // Use logo from assets - file is x-logo.avif
        return 'assets/integration_app_logos/x-logo.avif';
      case IntegrationApp.github:
        // Use logo from assets - file is github-logo.png
        return 'assets/integration_app_logos/github-logo.png';
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
      case IntegrationApp.github:
        return FontAwesomeIcons.github; // GitHub icon
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
      case IntegrationApp.github:
        return const Color(0xFF24292E); // GitHub brand color (dark gray)
    }
  }

  bool get isAvailable {
    //  return true; // All integrations are available
    return this != IntegrationApp.googleCalendar;
  }

  String get comingSoonText {
    return 'Coming Soon';
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
    // IntegrationProvider.loadFromBackend() already fetches all connection statuses
    // and syncs SharedPreferences for backward compatibility with services
    await context.read<IntegrationProvider>().loadFromBackend();
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

    if (app == IntegrationApp.github) {
      final service = GitHubService();
      final handled = await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
      if (handled) {
        // After successful auth, settings will be opened in didChangeAppLifecycleState
        return;
      }
    }
  }

  Future<bool> _handleAuthFlow(IntegrationApp app, bool isAuthenticated, Future<bool> Function() authenticate) async {
    if (isAuthenticated) return false;

    final shouldAuth = await _showAuthDialog(app);
    if (shouldAuth == true) {
      // Capture ScaffoldMessenger before async operation to avoid use_build_context_synchronously
      final scaffoldMessenger = ScaffoldMessenger.of(context);

      final success = await authenticate();
      if (success) {
        if (mounted) {
          scaffoldMessenger.showSnackBar(
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
          scaffoldMessenger.showSnackBar(
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
        await _handleDisconnect(app, GoogleCalendarService().disconnect);
      } else if (app == IntegrationApp.whoop) {
        await _handleDisconnect(app, WhoopService().disconnect);
      } else if (app == IntegrationApp.notion) {
        await _handleDisconnect(app, NotionService().disconnect);
      } else if (app == IntegrationApp.twitter) {
        await _handleDisconnect(app, TwitterService().disconnect);
      } else if (app == IntegrationApp.github) {
        await _handleDisconnect(app, GitHubService().disconnect);
      }
    }
  }

  Future<void> _handleDisconnect(IntegrationApp app, Future<bool> Function() disconnect) async {
    // Capture instances before async operation to avoid use_build_context_synchronously
    final integrationProvider = context.read<IntegrationProvider>();
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final success = await disconnect();
    if (success) {
      if (mounted) {
        await integrationProvider.deleteConnection(app.key);
      }
      if (mounted) {
        scaffoldMessenger.showSnackBar(
          SnackBar(
            content: Text('Disconnected from ${app.displayName}'),
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } else {
      if (mounted) {
        scaffoldMessenger.showSnackBar(
          const SnackBar(
            content: Text('Failed to disconnect'),
            backgroundColor: Colors.red,
            duration: Duration(seconds: 3),
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

  Widget _buildOverlappingLogo(String path, double size) {
    return Container(
      width: size,
      height: size,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.asset(
          path,
          width: size,
          height: size,
          fit: BoxFit.contain,
        ),
      ),
    );
  }

  Widget _buildShimmerButton() {
    return Shimmer.fromColors(
      baseColor: Colors.grey.shade800,
      highlightColor: Colors.grey.shade600,
      child: Container(
        width: 70,
        height: 28,
        decoration: BoxDecoration(
          color: Colors.grey.shade800,
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    );
  }

  Widget _buildAppTile(IntegrationApp app, bool isLoading) {
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    return GestureDetector(
      onTap: isAvailable && !isLoading
          ? () {
              if (isConnected) {
                // If GitHub is connected, open settings page
                if (app == IntegrationApp.github) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const GitHubSettingsPage(),
                    ),
                  );
                } else {
                  // For other apps, show disconnect dialog
                  _disconnectApp(app);
                }
              } else {
                _connectApp(app);
              }
            }
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
        child: Row(
          children: [
            // App Icon/Logo - Stacked for Google, single for others
            app == IntegrationApp.googleCalendar
                ? SizedBox(
                    width: 68, // Width for 2 overlapping logos (40px icon + 28px offset)
                    height: 40,
                    child: Stack(
                      children: [
                        // Gmail logo
                        Positioned(
                          left: 0,
                          child: _buildOverlappingLogo(
                            'assets/integration_app_logos/gmail-logo.jpeg',
                            40,
                          ),
                        ),
                        // Calendar logo
                        Positioned(
                          left: 28,
                          child: _buildOverlappingLogo(
                            'assets/integration_app_logos/google-calendar.png',
                            40,
                          ),
                        ),
                      ],
                    ),
                  )
                : Container(
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
                  !isAvailable ? 'Coming Soon' : 'Connect',
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
                'Create Your Own App',
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
        title: const Text(
          'Chat Tools',
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
                  children: [
                    ...IntegrationApp.values.map((app) => _buildAppTile(app, isLoading)).toList(),
                    _buildCreateYourOwnAppTile(),
                  ],
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
