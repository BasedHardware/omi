import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';

class AsanaSettingsPage extends StatefulWidget {
  const AsanaSettingsPage({super.key});

  @override
  State<AsanaSettingsPage> createState() => _AsanaSettingsPageState();
}

class _AsanaSettingsPageState extends State<AsanaSettingsPage> {
  final AsanaService _asanaService = AsanaService();
  List<Map<String, dynamic>> _workspaces = [];
  List<Map<String, dynamic>> _projects = [];
  bool _isLoadingWorkspaces = true;
  bool _isLoadingProjects = false;
  String? _selectedWorkspaceGid;
  String? _selectedProjectGid;

  @override
  void initState() {
    super.initState();
    _initializeAsana();
  }

  Future<void> _initializeAsana() async {
    // Ensure user info is fetched
    await _asanaService.refreshCurrentUser();
    await _loadWorkspaces();
  }

  Future<void> _loadWorkspaces() async {
    setState(() => _isLoadingWorkspaces = true);

    final workspaces = await _asanaService.getWorkspaces();
    final savedWorkspaceGid = SharedPreferencesUtil().asanaWorkspaceGid;

    setState(() {
      _workspaces = workspaces;
      _isLoadingWorkspaces = false;
      _selectedWorkspaceGid = savedWorkspaceGid;
    });

    // Load projects if workspace is selected
    if (_selectedWorkspaceGid != null) {
      await _loadProjects(_selectedWorkspaceGid!);
    } else if (workspaces.isNotEmpty) {
      // Auto-select first workspace
      _selectWorkspace(workspaces.first);
    }
  }

  Future<void> _loadProjects(String workspaceGid) async {
    setState(() => _isLoadingProjects = true);

    final projects = await _asanaService.getProjects(workspaceGid);
    final savedProjectGid = SharedPreferencesUtil().asanaProjectGid;

    setState(() {
      _projects = projects;
      _isLoadingProjects = false;
      _selectedProjectGid = savedProjectGid;
    });
  }

  void _selectWorkspace(Map<String, dynamic> workspace) async {
    final workspaceGid = workspace['gid'] as String;
    final workspaceName = workspace['name'] as String;

    setState(() {
      _selectedWorkspaceGid = workspaceGid;
      _selectedProjectGid = null; // Clear project when workspace changes
    });

    SharedPreferencesUtil().asanaWorkspaceGid = workspaceGid;
    SharedPreferencesUtil().asanaWorkspaceName = workspaceName;
    SharedPreferencesUtil().asanaProjectGid = null;
    SharedPreferencesUtil().asanaProjectName = null;

    await _loadProjects(workspaceGid);
  }

  void _selectProject(Map<String, dynamic> project) {
    final projectGid = project['gid'] as String;
    final projectName = project['name'] as String;

    setState(() {
      _selectedProjectGid = projectGid;
    });

    SharedPreferencesUtil().asanaProjectGid = projectGid;
    SharedPreferencesUtil().asanaProjectName = projectName;
  }

  void _clearProject() {
    setState(() {
      _selectedProjectGid = null;
    });

    SharedPreferencesUtil().asanaProjectGid = null;
    SharedPreferencesUtil().asanaProjectName = null;
  }

  Future<void> _disconnectAsana() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: const Text(
            'Disconnect from Asana?',
            style: TextStyle(color: Colors.white),
          ),
          content: const Text(
            'This will remove your Asana authentication and settings. You\'ll need to reconnect and reconfigure.',
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
      await _asanaService.disconnect();

      if (mounted) {
        // Also clear from task integrations if Asana was selected
        if (SharedPreferencesUtil().selectedTaskIntegration == 'asana') {
          // Default to Google Tasks on Android, Apple Reminders on Apple platforms
          final defaultApp = PlatformService.isApple ? 'apple_reminders' : 'google_tasks';
          SharedPreferencesUtil().selectedTaskIntegration = defaultApp;
          debugPrint('✓ Task integration disabled: Asana - switched to $defaultApp');
        }

        // Trigger provider refresh to update UI
        context.read<TaskIntegrationProvider>().refresh();

        Navigator.of(context).pop(); // Go back to task integrations

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Disconnected from Asana'),
            duration: Duration(seconds: 2),
          ),
        );
      }
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
          'Asana Settings',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _initializeAsana,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: SafeArea(
        child: _isLoadingWorkspaces
            ? const Center(child: CircularProgressIndicator())
            : SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Debug info
                    if (SharedPreferencesUtil().asanaUserGid != null)
                      Container(
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(bottom: 16),
                        decoration: BoxDecoration(
                          color: Colors.green.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.green.withOpacity(0.3)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.check_circle, color: Colors.green, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Connected as user: ${SharedPreferencesUtil().asanaUserGid}',
                                style: const TextStyle(
                                  color: Colors.green,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),

                    // Workspace Section
                    const Text(
                      'Default Workspace',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Tasks will be created in this workspace',
                      style: TextStyle(
                        color: Color(0xFF8E8E93),
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Workspace List
                    ..._workspaces.map((workspace) {
                      final workspaceGid = workspace['gid'] as String;
                      final workspaceName = workspace['name'] as String;
                      final isSelected = _selectedWorkspaceGid == workspaceGid;

                      return GestureDetector(
                        onTap: () => _selectWorkspace(workspace),
                        child: Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1C1C1E),
                            borderRadius: BorderRadius.circular(12),
                            border: isSelected ? Border.all(color: Colors.white, width: 2) : null,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  workspaceName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                  ),
                                ),
                              ),
                              if (isSelected)
                                const Icon(
                                  Icons.check_circle,
                                  color: Colors.white,
                                  size: 24,
                                ),
                            ],
                          ),
                        ),
                      );
                    }).toList(),

                    const SizedBox(height: 32),

                    // Project Section
                    if (_selectedWorkspaceGid != null) ...[
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Default Project (Optional)',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          if (_selectedProjectGid != null)
                            TextButton(
                              onPressed: _clearProject,
                              child: const Text(
                                'Clear',
                                style: TextStyle(color: Colors.red),
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Leave unselected to create tasks without a project',
                        style: TextStyle(
                          color: Color(0xFF8E8E93),
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(height: 16),

                      // Project List
                      if (_isLoadingProjects)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(20),
                            child: CircularProgressIndicator(),
                          ),
                        )
                      else if (_projects.isEmpty)
                        Container(
                          padding: const EdgeInsets.all(20),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1C1C1E),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Center(
                            child: Text(
                              'No projects found in this workspace',
                              style: TextStyle(
                                color: Color(0xFF8E8E93),
                                fontSize: 14,
                              ),
                            ),
                          ),
                        )
                      else
                        ..._projects.map((project) {
                          final projectGid = project['gid'] as String;
                          final projectName = project['name'] as String;
                          final isSelected = _selectedProjectGid == projectGid;

                          return GestureDetector(
                            onTap: () => _selectProject(project),
                            child: Container(
                              margin: const EdgeInsets.only(bottom: 12),
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1C1C1E),
                                borderRadius: BorderRadius.circular(12),
                                border: isSelected ? Border.all(color: Colors.white, width: 2) : null,
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      projectName,
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                      ),
                                    ),
                                  ),
                                  if (isSelected)
                                    const Icon(
                                      Icons.check_circle,
                                      color: Colors.white,
                                      size: 24,
                                    ),
                                ],
                              ),
                            ),
                          );
                        }).toList(),
                    ],

                    const SizedBox(height: 32),

                    // Disconnect Button
                    GestureDetector(
                      onTap: _disconnectAsana,
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
                              'Disconnect from Asana',
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
