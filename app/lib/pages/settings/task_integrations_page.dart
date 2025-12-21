import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/asana_settings_page.dart';
import 'package:omi/pages/settings/clickup_settings_page.dart';
import 'package:omi/pages/settings/google_tasks_settings_page.dart';
import 'package:omi/pages/settings/todoist_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/services/google_tasks_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

enum TaskIntegrationApp {
  appleReminders,
  todoist,
  clickup,
  asana,
  googleTasks,
  trello,
  monday,
}

extension TaskIntegrationAppExtension on TaskIntegrationApp {
  String get displayName {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'Apple Reminders';
      case TaskIntegrationApp.googleTasks:
        return 'Google Tasks';
      case TaskIntegrationApp.clickup:
        return 'ClickUp';
      case TaskIntegrationApp.asana:
        return 'Asana';
      case TaskIntegrationApp.trello:
        return 'Trello';
      case TaskIntegrationApp.todoist:
        return 'Todoist';
      case TaskIntegrationApp.monday:
        return 'Monday';
    }
  }

  String get key {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return 'apple_reminders';
      case TaskIntegrationApp.googleTasks:
        return 'google_tasks';
      case TaskIntegrationApp.clickup:
        return 'clickup';
      case TaskIntegrationApp.asana:
        return 'asana';
      case TaskIntegrationApp.trello:
        return 'trello';
      case TaskIntegrationApp.todoist:
        return 'todoist';
      case TaskIntegrationApp.monday:
        return 'monday';
    }
  }

  String? get logoPath {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return Assets.images.appleRemindersLogo.path;
      case TaskIntegrationApp.googleTasks:
        return Assets.integrationAppLogos.googleTasksLogo.path;
      case TaskIntegrationApp.clickup:
        return Assets.integrationAppLogos.clickupLogo.path;
      case TaskIntegrationApp.asana:
        return Assets.integrationAppLogos.asanaLogo.path;
      case TaskIntegrationApp.trello:
        return Assets.integrationAppLogos.trelloLogo.path;
      case TaskIntegrationApp.todoist:
        return Assets.integrationAppLogos.todoistLogo.path;
      case TaskIntegrationApp.monday:
        return Assets.integrationAppLogos.mondayLogo.path;
    }
  }

  IconData get icon {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return Icons.checklist_rounded;
      case TaskIntegrationApp.googleTasks:
        return Icons.task_alt;
      case TaskIntegrationApp.clickup:
        return Icons.rocket_launch;
      case TaskIntegrationApp.asana:
        return Icons.analytics_outlined;
      case TaskIntegrationApp.trello:
        return Icons.dashboard_outlined;
      case TaskIntegrationApp.todoist:
        return Icons.check_circle_outline;
      case TaskIntegrationApp.monday:
        return Icons.calendar_today;
    }
  }

  Color get iconColor {
    switch (this) {
      case TaskIntegrationApp.appleReminders:
        return const Color(0xFF007AFF);
      case TaskIntegrationApp.googleTasks:
        return const Color(0xFF4285F4);
      case TaskIntegrationApp.clickup:
        return const Color(0xFF7B68EE);
      case TaskIntegrationApp.asana:
        return const Color(0xFFF06A6A);
      case TaskIntegrationApp.trello:
        return const Color(0xFF0079BF);
      case TaskIntegrationApp.todoist:
        return const Color(0xFFE44332);
      case TaskIntegrationApp.monday:
        return const Color(0xFFFF3D57);
    }
  }

  bool get isAvailable {
    // Apple Reminders, Todoist, Asana, and ClickUp are available
    return this == TaskIntegrationApp.appleReminders ||
        this == TaskIntegrationApp.todoist ||
        this == TaskIntegrationApp.asana ||
        this == TaskIntegrationApp.clickup;
  }

  String get comingSoonText {
    return 'Coming Soon';
  }
}

class TaskIntegrationsPage extends StatefulWidget {
  const TaskIntegrationsPage({super.key});

  @override
  State<TaskIntegrationsPage> createState() => _TaskIntegrationsPageState();
}

class _TaskIntegrationsPageState extends State<TaskIntegrationsPage> with WidgetsBindingObserver {
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
    await context.read<TaskIntegrationProvider>().loadFromBackend();
  }

  bool _shouldShowSettingsIcon() {
    final selected = context.read<TaskIntegrationProvider>().selectedApp;
    final hasSettings = (selected == TaskIntegrationApp.asana && AsanaService().isAuthenticated) ||
        (selected == TaskIntegrationApp.clickup && ClickUpService().isAuthenticated) ||
        (selected == TaskIntegrationApp.todoist && TodoistService().isAuthenticated) ||
        (selected == TaskIntegrationApp.googleTasks && GoogleTasksService().isAuthenticated);
    return hasSettings;
  }

  void _openSelectedAppSettings() {
    final selected = context.read<TaskIntegrationProvider>().selectedApp;
    if (selected == TaskIntegrationApp.asana && AsanaService().isAuthenticated) {
      MixpanelManager().taskIntegrationSettingsOpened(appName: 'asana');
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => const AsanaSettingsPage(),
        ),
      );
    } else if (selected == TaskIntegrationApp.clickup && ClickUpService().isAuthenticated) {
      MixpanelManager().taskIntegrationSettingsOpened(appName: 'clickup');
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => const ClickUpSettingsPage(),
        ),
      );
    } else if (selected == TaskIntegrationApp.todoist && TodoistService().isAuthenticated) {
      MixpanelManager().taskIntegrationSettingsOpened(appName: 'todoist');
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => const TodoistSettingsPage(),
        ),
      );
    } else if (selected == TaskIntegrationApp.googleTasks && GoogleTasksService().isAuthenticated) {
      MixpanelManager().taskIntegrationSettingsOpened(appName: 'google_tasks');
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (context) => const GoogleTasksSettingsPage(),
        ),
      );
    }
  }

  Future<void> _selectApp(TaskIntegrationApp app) async {
    if (!app.isAvailable) {
      _showComingSoonDialog(app);
      return;
    }

    // Check if Todoist requires authentication
    if (app == TaskIntegrationApp.todoist) {
      final todoistService = TodoistService();
      if (!todoistService.isAuthenticated) {
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth == true) {
          final success = await todoistService.authenticate();
          if (success) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Please complete authentication in your browser. Once done, return to the app.'),
                  duration: Duration(seconds: 5),
                ),
              );
            }
            await context.read<TaskIntegrationProvider>().setSelectedApp(app);
            // Note: OAuth callback will save connection to Firebase
            // Provider will refresh when user returns to this page
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            MixpanelManager().taskIntegrationAuthFailed(
              appName: 'todoist',
            );

            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Failed to start Todoist authentication'),
                  backgroundColor: Colors.red,
                  duration: Duration(seconds: 3),
                ),
              );
            }
          }
        }
        return;
      }
    }

    // Check if Asana requires authentication
    if (app == TaskIntegrationApp.asana) {
      final asanaService = AsanaService();
      if (!asanaService.isAuthenticated) {
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth == true) {
          final success = await asanaService.authenticate();
          if (success) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Please complete authentication in your browser. Once done, return to the app.'),
                  duration: Duration(seconds: 5),
                ),
              );
            }
            await context.read<TaskIntegrationProvider>().setSelectedApp(app);
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            MixpanelManager().taskIntegrationAuthFailed(
              appName: 'asana',
            );

            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Failed to start Asana authentication'),
                  backgroundColor: Colors.red,
                  duration: Duration(seconds: 3),
                ),
              );
            }
          }
        }
        return;
      }
    }

    // Check if Google Tasks requires authentication
    if (app == TaskIntegrationApp.googleTasks) {
      final googleTasksService = GoogleTasksService();
      if (!googleTasksService.isAuthenticated) {
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth == true) {
          final success = await googleTasksService.authenticate();
          if (success) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Please complete authentication in your browser. Once done, return to the app.'),
                  duration: Duration(seconds: 5),
                ),
              );
            }
            await context.read<TaskIntegrationProvider>().setSelectedApp(app);
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            MixpanelManager().taskIntegrationAuthFailed(
              appName: 'google_tasks',
            );

            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Failed to start Google Tasks authentication'),
                  backgroundColor: Colors.red,
                  duration: Duration(seconds: 3),
                ),
              );
            }
          }
        }
        return;
      }
    }

    // Check if ClickUp requires authentication
    if (app == TaskIntegrationApp.clickup) {
      final clickupService = ClickUpService();
      if (!clickupService.isAuthenticated) {
        final shouldAuth = await _showAuthDialog(app);
        if (shouldAuth == true) {
          final success = await clickupService.authenticate();
          if (success) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Please complete authentication in your browser. Once done, return to the app.'),
                  duration: Duration(seconds: 5),
                ),
              );
            }
            await context.read<TaskIntegrationProvider>().setSelectedApp(app);
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
            // Track authentication failure
            MixpanelManager().taskIntegrationAuthFailed(
              appName: 'clickup',
            );

            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Failed to start ClickUp authentication'),
                  backgroundColor: Colors.red,
                  duration: Duration(seconds: 3),
                ),
              );
            }
          }
        }
        return;
      }
    }

    // Save to backend via provider
    await context.read<TaskIntegrationProvider>().setSelectedApp(app);

    // Log app selection
    debugPrint('✓ Task integration selected: ${app.displayName} (${app.key})');
  }

  Future<bool?> _showAuthDialog(TaskIntegrationApp app) {
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
            'You\'ll need to authorize Omi to create tasks in your ${app.displayName} account. This will open your browser for authentication.',
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

  void _showComingSoonDialog(TaskIntegrationApp app) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: Text(
            '${app.displayName} Integration',
            style: const TextStyle(color: Colors.white),
          ),
          content: Text(
            'Integration with ${app.displayName} is coming soon! We\'re working hard to bring you more task management options.',
            style: const TextStyle(color: Color(0xFF8E8E93)),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text(
                'Got it',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );
  }

  bool _isAppConnected(TaskIntegrationApp app) {
    // Use provider to get connection status so it updates reactively
    return context.read<TaskIntegrationProvider>().isAppConnected(app);
  }

  String _getHeroTag(TaskIntegrationApp app) {
    // Return Hero tag for apps shown in the banner
    switch (app) {
      case TaskIntegrationApp.todoist:
        return 'task_integration_todoist_icon';
      case TaskIntegrationApp.clickup:
        return 'task_integration_clickup_icon';
      case TaskIntegrationApp.asana:
        return 'task_integration_asana_icon';
      default:
        // Unique tag for apps not in banner
        return 'task_integration_${app.key}_icon';
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

  Widget _buildAppTile(TaskIntegrationApp app, bool isLoading) {
    final isSelected = context.read<TaskIntegrationProvider>().selectedApp == app;
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    return GestureDetector(
      onTap: isAvailable && !isLoading
          ? () {
              // If already connected and selected, open settings
              if (isConnected && isSelected) {
                if (app == TaskIntegrationApp.asana) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const AsanaSettingsPage(),
                    ),
                  );
                } else if (app == TaskIntegrationApp.clickup) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const ClickUpSettingsPage(),
                    ),
                  );
                } else if (app == TaskIntegrationApp.todoist) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const TodoistSettingsPage(),
                    ),
                  );
                } else if (app == TaskIntegrationApp.googleTasks) {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (context) => const GoogleTasksSettingsPage(),
                    ),
                  );
                }
              } else {
                _selectApp(app);
              }
            }
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
        child: Row(
          children: [
            // App Icon (with Hero animation for banner icons)
            Hero(
              tag: _getHeroTag(app),
              child: Container(
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
            // Action Button - Show shimmer while loading (except for Apple Reminders which is always connected)
            if (isLoading && app != TaskIntegrationApp.appleReminders)
              _buildShimmerButton()
            else if (!isAvailable)
              // Coming Soon button
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFF3C3C43),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'Coming Soon',
                  style: TextStyle(
                    color: Color(0xFF8E8E93),
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              )
            else if (!isConnected)
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
            // Radio button for connected services
            if (isSelected)
              const FaIcon(
                FontAwesomeIcons.solidCircleCheck,
                color: Colors.green,
                size: 24,
              )
            else
              Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: const Color(0xFF3C3C43),
                    width: 2,
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
    final provider = context.watch<TaskIntegrationProvider>();
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
          'Task Integrations',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        actions: [
          // Settings icon for apps that have configuration options
          if (_shouldShowSettingsIcon())
            IconButton(
              icon: const Icon(Icons.settings, color: Colors.white),
              onPressed: _openSelectedAppSettings,
              tooltip: 'Configure Settings',
            ),
        ],
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
                  children: TaskIntegrationApp.values
                      .where((app) {
                        // Hide Apple Reminders on Android
                        if (app == TaskIntegrationApp.appleReminders && !PlatformService.isApple) {
                          return false;
                        }
                        return true;
                      })
                      .map((app) => _buildAppTile(app, isLoading))
                      .toList(),
                ),
              ),
              const SizedBox(height: 16),

              // Footer Note
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.yellow.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    FaIcon(
                      FontAwesomeIcons.solidLightbulb,
                      color: Colors.yellow.withValues(alpha: 0.5),
                      size: 20,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Tasks can be exported to one app at a time.',
                        style: const TextStyle(
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
