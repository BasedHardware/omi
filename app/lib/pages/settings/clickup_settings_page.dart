import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

class ClickUpSettingsPage extends StatefulWidget {
  const ClickUpSettingsPage({super.key});

  @override
  State<ClickUpSettingsPage> createState() => _ClickUpSettingsPageState();
}

class _ClickUpSettingsPageState extends State<ClickUpSettingsPage> {
  final ClickUpService _clickupService = ClickUpService();
  List<Map<String, dynamic>> _teams = [];
  List<Map<String, dynamic>> _spaces = [];
  List<Map<String, dynamic>> _lists = [];
  bool _isLoadingTeams = true;
  bool _isLoadingSpaces = false;
  bool _isLoadingLists = false;
  String? _selectedTeamId;
  String? _selectedSpaceId;
  String? _selectedListId;

  @override
  void initState() {
    super.initState();
    _initializeClickUp();
  }

  Future<void> _initializeClickUp() async {
    await _loadTeams();
  }

  Future<void> _loadTeams() async {
    setState(() => _isLoadingTeams = true);

    final teams = await _clickupService.getWorkspaces();

    if (!mounted) return;

    // Get saved team from Firebase (via provider)
    final provider = context.read<TaskIntegrationProvider>();
    final clickupDetails = provider.getConnectionDetails('clickup');
    final savedTeamId = clickupDetails?['team_id'] as String?;

    setState(() {
      _teams = teams;
      _isLoadingTeams = false;
      _selectedTeamId = savedTeamId;
    });

    if (_selectedTeamId != null) {
      await _loadSpaces(_selectedTeamId!);
    } else if (teams.isNotEmpty) {
      _selectTeam(teams.first);
    }
  }

  Future<void> _loadSpaces(String teamId) async {
    setState(() => _isLoadingSpaces = true);

    final spaces = await _clickupService.getSpaces(teamId);

    if (!mounted) return;

    // Get saved space from Firebase (via provider)
    final provider = context.read<TaskIntegrationProvider>();
    final clickupDetails = provider.getConnectionDetails('clickup');
    final savedSpaceId = clickupDetails?['space_id'] as String?;

    setState(() {
      _spaces = spaces;
      _isLoadingSpaces = false;
      _selectedSpaceId = savedSpaceId;
    });

    if (_selectedSpaceId != null) {
      await _loadLists(_selectedSpaceId!);
    }
  }

  Future<void> _loadLists(String spaceId) async {
    setState(() => _isLoadingLists = true);

    final lists = await _clickupService.getLists(spaceId);

    if (!mounted) return;

    // Get saved list from Firebase (via provider)
    final provider = context.read<TaskIntegrationProvider>();
    final clickupDetails = provider.getConnectionDetails('clickup');
    final savedListId = clickupDetails?['list_id'] as String?;

    setState(() {
      _lists = lists;
      _isLoadingLists = false;
      _selectedListId = savedListId;
    });
  }

  void _selectTeam(Map<String, dynamic> team) async {
    final teamId = team['id'].toString();
    final teamName = team['name'] as String;

    setState(() {
      _selectedTeamId = teamId;
      _selectedSpaceId = null;
      _selectedListId = null;
    });

    // Get current integration details and update with new team
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('clickup') ?? {};

    await provider.saveConnectionDetails('clickup', {
      ...currentDetails,
      'connected': true,
      'team_id': teamId,
      'team_name': teamName,
      'space_id': null,
      'space_name': null,
      'list_id': null,
      'list_name': null,
    });

    await _loadSpaces(teamId);
  }

  void _selectSpace(Map<String, dynamic> space) async {
    final spaceId = space['id'].toString();
    final spaceName = space['name'] as String;

    setState(() {
      _selectedSpaceId = spaceId;
      _selectedListId = null;
    });

    // Get current integration details and update with new space
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('clickup') ?? {};

    await provider.saveConnectionDetails('clickup', {
      ...currentDetails,
      'connected': true,
      'space_id': spaceId,
      'space_name': spaceName,
      'list_id': null,
      'list_name': null,
    });

    await _loadLists(spaceId);
  }

  void _selectList(Map<String, dynamic> list) async {
    final listId = list['id'].toString();
    final listName = list['name'] as String;

    setState(() {
      _selectedListId = listId;
    });

    // Get current integration details and update with new list
    final provider = context.read<TaskIntegrationProvider>();
    final currentDetails = provider.getConnectionDetails('clickup') ?? {};

    await provider.saveConnectionDetails('clickup', {
      ...currentDetails,
      'connected': true,
      'list_id': listId,
      'list_name': listName,
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingTeams) {
      return const Scaffold(
        backgroundColor: Color(0xFF000000),
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return IntegrationSettingsPage(
      appName: 'ClickUp',
      appKey: 'clickup',
      disconnectService: _clickupService.disconnect,
      showRefresh: true,
      onRefresh: _initializeClickUp,
      children: [
        if (_clickupService.currentUserId != null)
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
                    context.l10n.connectedAsUser(_clickupService.currentUserId!),
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
        ..._teams.map((team) {
          final teamId = team['id'].toString();
          final teamName = team['name'] as String;
          final isSelected = _selectedTeamId == teamId;
          return GestureDetector(
            onTap: () => _selectTeam(team),
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
                      teamName,
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
        if (_selectedTeamId != null) ...[
          Text(
            context.l10n.defaultSpace,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.selectSpaceInWorkspace,
            style: const TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 16),
          if (_isLoadingSpaces)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: CircularProgressIndicator(),
              ),
            )
          else if (_spaces.isEmpty)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: Text(
                  context.l10n.noSpacesInWorkspace,
                  style: const TextStyle(
                    color: Color(0xFF8E8E93),
                    fontSize: 14,
                  ),
                ),
              ),
            )
          else
            ..._spaces.map((space) {
              final spaceId = space['id'].toString();
              final spaceName = space['name'] as String;
              final isSelected = _selectedSpaceId == spaceId;
              return GestureDetector(
                onTap: () => _selectSpace(space),
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
                          spaceName,
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
        ],
        if (_selectedSpaceId != null) ...[
          Text(
            context.l10n.defaultList,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.tasksAddedToList,
            style: const TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 16),
          if (_isLoadingLists)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: CircularProgressIndicator(),
              ),
            )
          else if (_lists.isEmpty)
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: Text(
                  context.l10n.noListsInSpace,
                  style: const TextStyle(
                    color: Color(0xFF8E8E93),
                    fontSize: 14,
                  ),
                ),
              ),
            )
          else
            ..._lists.map((list) {
              final listId = list['id'].toString();
              final listName = list['name'] as String;
              final isSelected = _selectedListId == listId;
              return GestureDetector(
                onTap: () => _selectList(list),
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
                          listName,
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
        ],
      ],
    );
  }
}
