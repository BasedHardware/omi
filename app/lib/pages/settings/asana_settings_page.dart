import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/integration_selection_card.dart';
import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/integrations/asana_service.dart';
import 'package:omi/ui/ui.dart';
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
      // Give the first load the same header as the loaded page, so it can always be left.
      return Scaffold(
        appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.appSettings('Asana'))),
        body: const OmiLoadingState(),
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
          IntegrationConnectedBanner(context.l10n.connectedAsUser(_asanaService.currentUserGid!)),
        Text(
          context.l10n.defaultWorkspace,
          style: OmiType.title3,
        ),
        const SizedBox(height: OmiSpacing.xs),
        Text(context.l10n.tasksCreatedInWorkspace, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
        const SizedBox(height: OmiSpacing.md),
        ..._workspaces.map((workspace) {
          final workspaceGid = workspace['gid'] as String;
          final workspaceName = workspace['name'] as String;
          final isSelected = _selectedWorkspaceGid == workspaceGid;
          return IntegrationSelectionCard(
            label: workspaceName,
            isSelected: isSelected,
            onTap: () => _selectWorkspace(workspace),
          );
        }),
        const SizedBox(height: OmiSpacing.xxl),
        if (_selectedWorkspaceGid != null) ...[
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(child: Text(context.l10n.defaultProjectOptional, style: OmiType.title3)),
              if (_selectedProjectGid != null)
                OmiButton.tertiary(label: context.l10n.clear, onPressed: _clearProject, size: OmiButtonSize.compact),
            ],
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(context.l10n.leaveUnselectedTasks, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          const SizedBox(height: OmiSpacing.md),
          if (_isLoadingProjects)
            const Center(
              child: Padding(padding: EdgeInsets.all(OmiSpacing.lg), child: OmiSpinner()),
            )
          else if (_projects.isEmpty)
            IntegrationSelectionEmpty(context.l10n.noProjectsInWorkspace)
          else
            ..._projects.map((project) {
              final projectGid = project['gid'] as String;
              final projectName = project['name'] as String;
              final isSelected = _selectedProjectGid == projectGid;
              return IntegrationSelectionCard(
                label: projectName,
                isSelected: isSelected,
                onTap: () => _selectProject(project),
              );
            }),
        ],
      ],
    );
  }
}
