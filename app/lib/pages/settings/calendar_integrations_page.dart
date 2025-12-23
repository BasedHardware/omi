import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/services/google_calendar_service.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

enum CalendarApp {
  googleCalendar,
  outlook,
}

extension CalendarAppExtension on CalendarApp {
  String get displayName {
    switch (this) {
      case CalendarApp.googleCalendar:
        return 'Google Calendar';
      case CalendarApp.outlook:
        return 'Outlook';
    }
  }

  String get key {
    switch (this) {
      case CalendarApp.googleCalendar:
        return 'google_calendar';
      case CalendarApp.outlook:
        return 'outlook';
    }
  }

  String? get logoPath {
    switch (this) {
      case CalendarApp.googleCalendar:
        return 'assets/integration_app_logos/google-calendar.png';
      case CalendarApp.outlook:
        return 'assets/integration_app_logos/outlook-logo.jpeg';
    }
  }

  IconData get icon {
    switch (this) {
      case CalendarApp.googleCalendar:
        return Icons.calendar_today;
      case CalendarApp.outlook:
        return FontAwesomeIcons.microsoft;
    }
  }

  Color get iconColor {
    switch (this) {
      case CalendarApp.googleCalendar:
        return const Color(0xFF4285F4);
      case CalendarApp.outlook:
        return const Color(0xFF0078D4); // Microsoft/Outlook blue
    }
  }

  bool get isAvailable {
    switch (this) {
      case CalendarApp.googleCalendar:
        return true;
      case CalendarApp.outlook:
        return false; // Coming soon
    }
  }
}

class CalendarIntegrationsPage extends StatefulWidget {
  const CalendarIntegrationsPage({super.key});

  @override
  State<CalendarIntegrationsPage> createState() => _CalendarIntegrationsPageState();
}

class _CalendarIntegrationsPageState extends State<CalendarIntegrationsPage> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
  }

  Future<void> _connectApp(CalendarApp app) async {
    if (!app.isAvailable) {
      return;
    }

    if (app == CalendarApp.googleCalendar) {
      final service = GoogleCalendarService();
      await _handleAuthFlow(app, service.isAuthenticated, service.authenticate);
    }
  }

  Future<bool> _handleAuthFlow(CalendarApp app, bool isAuthenticated, Future<bool> Function() authenticate) async {
    if (isAuthenticated) return false;

    final shouldAuth = await _showAuthDialog(app);
    if (shouldAuth == true) {
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
        debugPrint('✓ Calendar integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
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

  Future<void> _disconnectApp(CalendarApp app) async {
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
      if (app == CalendarApp.googleCalendar) {
        await _handleDisconnect(app, GoogleCalendarService().disconnect);
      }
    }
  }

  Future<void> _handleDisconnect(CalendarApp app, Future<bool> Function() disconnect) async {
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

  Future<bool?> _showAuthDialog(CalendarApp app) {
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
            'You\'ll need to authorize Omi to access your ${app.displayName}. This will open your browser for authentication.',
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

  bool _isAppConnected(CalendarApp app) {
    // Use the same integration provider to share status with Chat Tools
    final provider = context.read<IntegrationProvider>();
    switch (app) {
      case CalendarApp.googleCalendar:
        return provider.isAppConnected(IntegrationApp.googleCalendar);
      case CalendarApp.outlook:
        return false; // Not implemented yet
    }
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

  Widget _buildAppTile(CalendarApp app, bool isLoading) {
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    return GestureDetector(
      onTap: isAvailable && !isLoading
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
            if (isLoading && app.isAvailable)
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

  @override
  Widget build(BuildContext context) {
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
          'Calendar',
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
                    ...CalendarApp.values.map((app) => _buildAppTile(app, isLoading)).toList(),
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
                      FontAwesomeIcons.calendarCheck,
                      color: Colors.blue.withValues(alpha: 0.5),
                      size: 20,
                    ),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Text(
                        'Connect your calendar to automatically link conversations to meetings.',
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
