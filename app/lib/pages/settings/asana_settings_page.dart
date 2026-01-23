import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/asana_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
    // Load workspaces (user info is in Firebase)
    await _loadWorkspaces();
  }

  Future<void> _loadWorkspaces() async {
    setState(() => _isLoadingWorkspaces = true);

    final workspaces = await _asanaService.getWorkspaces();

    if (!mounted) return;

    // Get saved workspace from Firebase (via provider)
    final provider = context.read<TaskIntegrationProvider>();
    final asanaDetails = provider.getConnectionDetails('asana');
    final savedWorkspaceGid = asanaDetails?['workspace_gid'] as String?;

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

    if (!mounted) return;

    // Get saved project from Firebase (via provider)
    final provider = context.read<TaskIntegrationProvider>();
    final asanaDetails = provider.getConnectionDetails('asana');
    final savedProjectGid = asanaDetails?['project_gid'] as String?;

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

    // Get current integration details and update with new workspace
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('asana') ?? {};

    await provider.saveConnectionDetails('asana', {
      ...currentDetails,
      'connected': true,
      'workspace_gid': workspaceGid,
      'workspace_name': workspaceName,
      'project_gid': null,
      'project_name': null,
    });

    if (!mounted) return;

    await _loadProjects(workspaceGid);
  }

  void _selectProject(Map<String, dynamic> project) async {
    final projectGid = project['gid'] as String;
    final projectName = project['name'] as String;

    setState(() {
      _selectedProjectGid = projectGid;
    });

    // Get current integration details and update with new project
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('asana') ?? {};

    await provider.saveConnectionDetails('asana', {
      ...currentDetails,
      'connected': true,
      'project_gid': projectGid,
      'project_name': projectName,
    });
  }

  void _clearProject() async {
    setState(() {
      _selectedProjectGid = null;
    });

    // Get current integration details and clear project
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('asana') ?? {};

    await provider.saveConnectionDetails('asana', {
      ...currentDetails,
      'connected': true,
      'project_gid': null,
      'project_name': null,
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingWorkspaces) {
      return const Scaffold(
        backgroundColor: Color(0xFF000000),
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return IntegrationSettingsPage(
      appName: 'Asana',
      appKey: 'asana',
      disconnectService: _asanaService.disconnect,
      showRefresh: true,
      onRefresh: _initializeAsana,
      children: [
        if (_asanaService.currentUserGid != null)
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
                    context.l10n.connectedAsUser(_asanaService.currentUserGid!),
                    style: const TextStyle(
                      color: Colors.green,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
        Text(
          context.l10n.defaultWorkspace,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          context.l10n.tasksCreatedInWorkspace,
          style: const TextStyle(
            color: Color(0xFF8E8E93),
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 16),
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
        }),
        const SizedBox(height: 32),
        if (_selectedWorkspaceGid != null) ...[
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                context.l10n.defaultProjectOptional,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (_selectedProjectGid != null)
                TextButton(
                  onPressed: _clearProject,
                  child: Text(
                    context.l10n.clear,
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.leaveUnselectedTasks,
            style: const TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 16),
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
              child: Center(
                child: Text(
                  context.l10n.noProjectsInWorkspace,
                  style: const TextStyle(
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
            }),
        ],
      ],
    );
  }
}
