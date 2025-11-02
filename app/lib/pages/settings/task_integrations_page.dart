import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/asana_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:provider/provider.dart';

enum TaskIntegrationApp {
  appleReminders,
  googleTasks,
  clickup,
  asana,
  trello,
  todoist,
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
    // Apple Reminders, Todoist, and Asana are available
    return this == TaskIntegrationApp.appleReminders ||
        this == TaskIntegrationApp.todoist ||
        this == TaskIntegrationApp.asana;
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

class _TaskIntegrationsPageState extends State<TaskIntegrationsPage> {
  late TaskIntegrationApp _selectedApp;

  @override
  void initState() {
    super.initState();
    _loadSelectedApp();
  }

  void _loadSelectedApp() {
    final selectedKey = SharedPreferencesUtil().selectedTaskIntegration;
    _selectedApp = TaskIntegrationApp.values.firstWhere(
      (app) => app.key == selectedKey,
      orElse: () => TaskIntegrationApp.appleReminders,
    );
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
            setState(() {
              _selectedApp = app;
            });
            SharedPreferencesUtil().selectedTaskIntegration = app.key;
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
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
            setState(() {
              _selectedApp = app;
            });
            SharedPreferencesUtil().selectedTaskIntegration = app.key;
            debugPrint('✓ Task integration enabled: ${app.displayName} (${app.key}) - authentication in progress');
          } else {
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

    setState(() {
      _selectedApp = app;
    });
    SharedPreferencesUtil().selectedTaskIntegration = app.key;

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

  Widget _buildAppTile(TaskIntegrationApp app) {
    final isSelected = _selectedApp == app;
    final isAvailable = app.isAvailable;
    final isConnected = _isAppConnected(app);

    return GestureDetector(
      onTap: isAvailable
          ? () {
              // If Asana is already connected and selected, open settings
              if (app == TaskIntegrationApp.asana && isConnected && isSelected) {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (context) => const AsanaSettingsPage(),
                  ),
                );
              } else {
                _selectApp(app);
              }
            }
          : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
        child: Row(
          children: [
            // App Icon
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
            if (!isAvailable)
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
    context.watch<TaskIntegrationProvider>();

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
                  children: TaskIntegrationApp.values.map(_buildAppTile).toList(),
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
