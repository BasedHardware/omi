import 'package:flutter/material.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/todoist_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';

class TodoistSettingsPage extends StatefulWidget {
  const TodoistSettingsPage({super.key});

  @override
  State<TodoistSettingsPage> createState() => _TodoistSettingsPageState();
}

class _TodoistSettingsPageState extends State<TodoistSettingsPage> {
  final TodoistService _todoistService = TodoistService();

  Future<void> _disconnectTodoist() async {
    // Capture context references before any async operations
    final provider = context.read<TaskIntegrationProvider>();
    final navigator = Navigator.of(context);
    final scaffoldMessenger = ScaffoldMessenger.of(context);
    
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: const Text(
            'Disconnect from Todoist?',
            style: TextStyle(color: Colors.white),
          ),
          content: const Text(
            'This will remove your Todoist authentication. You\'ll need to reconnect to use it again.',
            style: TextStyle(color: Color(0xFF8E8E93)),
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
      await _todoistService.disconnect();

      if (!mounted) return;

      // Delete connection from Firebase
      await provider.deleteConnection('todoist');

      // Also clear from task integrations if Todoist was selected
      if (provider.selectedApp.key == 'todoist') {
        // Default to Google Tasks on Android, Apple Reminders on Apple platforms
        final defaultApp =
            PlatformService.isApple ? TaskIntegrationApp.appleReminders : TaskIntegrationApp.googleTasks;
        await provider.setSelectedApp(defaultApp);
        debugPrint('✓ Task integration disabled: Todoist - switched to ${defaultApp.key}');
      }

      provider.refresh();

      // Show snackbar before popping to avoid using deactivated context
      scaffoldMessenger.showSnackBar(
        const SnackBar(
          content: Text('Disconnected from Todoist'),
          duration: Duration(seconds: 2),
        ),
      );

      navigator.pop();
    }
  }

  @override
  Widget build(BuildContext context) {
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
          'Todoist Settings',
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
              // Connected Status
              Container(
                padding: const EdgeInsets.all(12),
                margin: const EdgeInsets.only(bottom: 24),
                decoration: BoxDecoration(
                  color: Colors.green.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.green.withOpacity(0.3)),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.check_circle, color: Colors.green, size: 16),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Connected to Todoist',
                        style: TextStyle(
                          color: Colors.green,
                          fontSize: 14,
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Info Section
              const Text(
                'Account',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Your action items will be synced to your Todoist account',
                style: TextStyle(
                  color: Color(0xFF8E8E93),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 32),

              const Spacer(),

              // Disconnect Button
              GestureDetector(
                onTap: _disconnectTodoist,
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red.withOpacity(0.3)),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.logout,
                        color: Colors.red,
                        size: 20,
                      ),
                      SizedBox(width: 12),
                      Text(
                        'Disconnect from Todoist',
                        style: TextStyle(
                          color: Colors.red,
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
