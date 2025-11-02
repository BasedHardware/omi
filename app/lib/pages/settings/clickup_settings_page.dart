import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/clickup_service.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:provider/provider.dart';

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
    await _clickupService.refreshCurrentUser();
    await _loadTeams();
  }

  Future<void> _loadTeams() async {
    setState(() => _isLoadingTeams = true);

    final teams = await _clickupService.getWorkspaces();
    final savedTeamId = SharedPreferencesUtil().clickupTeamId;

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
    final savedSpaceId = SharedPreferencesUtil().clickupSpaceId;

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
    final savedListId = SharedPreferencesUtil().clickupListId;

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

    SharedPreferencesUtil().clickupTeamId = teamId;
    SharedPreferencesUtil().clickupTeamName = teamName;
    SharedPreferencesUtil().clickupSpaceId = null;
    SharedPreferencesUtil().clickupSpaceName = null;
    SharedPreferencesUtil().clickupListId = null;
    SharedPreferencesUtil().clickupListName = null;

    await _loadSpaces(teamId);
  }

  void _selectSpace(Map<String, dynamic> space) async {
    final spaceId = space['id'].toString();
    final spaceName = space['name'] as String;

    setState(() {
      _selectedSpaceId = spaceId;
      _selectedListId = null;
    });

    SharedPreferencesUtil().clickupSpaceId = spaceId;
    SharedPreferencesUtil().clickupSpaceName = spaceName;
    SharedPreferencesUtil().clickupListId = null;
    SharedPreferencesUtil().clickupListName = null;

    await _loadLists(spaceId);
  }

  void _selectList(Map<String, dynamic> list) {
    final listId = list['id'].toString();
    final listName = list['name'] as String;

    setState(() {
      _selectedListId = listId;
    });

    SharedPreferencesUtil().clickupListId = listId;
    SharedPreferencesUtil().clickupListName = listName;
  }

  Future<void> _disconnectClickUp() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          title: const Text(
            'Disconnect from ClickUp?',
            style: TextStyle(color: Colors.white),
          ),
          content: const Text(
            'This will remove your ClickUp authentication and settings. You\'ll need to reconnect and reconfigure.',
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
      await _clickupService.disconnect();

      if (mounted) {
        if (SharedPreferencesUtil().selectedTaskIntegration == 'clickup') {
          // Default to Google Tasks on Android, Apple Reminders on Apple platforms
          final defaultApp = PlatformService.isApple ? 'apple_reminders' : 'google_tasks';
          SharedPreferencesUtil().selectedTaskIntegration = defaultApp;
          debugPrint('✓ Task integration disabled: ClickUp - switched to $defaultApp');
        }
        
        context.read<TaskIntegrationProvider>().refresh();
        Navigator.of(context).pop();

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Disconnected from ClickUp'),
            duration: Duration(seconds: 2),
          ),
        );
      }
    }
  }

  Widget _buildSelectionTile({
    required String title,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
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
                title,
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
          'ClickUp Settings',
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
            onPressed: _initializeClickUp,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: SafeArea(
        child: _isLoadingTeams
            ? const Center(child: CircularProgressIndicator())
            : SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Debug info
                    if (SharedPreferencesUtil().clickupUserId != null)
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
                                'Connected as user: ${SharedPreferencesUtil().clickupUserId}',
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

                    // Team List
                    ..._teams.map((team) {
                      final teamId = team['id'].toString();
                      final teamName = team['name'] as String;
                      final isSelected = _selectedTeamId == teamId;

                      return _buildSelectionTile(
                        title: teamName,
                        isSelected: isSelected,
                        onTap: () => _selectTeam(team),
                      );
                    }),

                    const SizedBox(height: 32),

                    // Space Section
                    if (_selectedTeamId != null) ...[
                      const Text(
                        'Default Space',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Select a space in your workspace',
                        style: TextStyle(
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
                          child: const Center(
                            child: Text(
                              'No spaces found in this workspace',
                              style: TextStyle(
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

                          return _buildSelectionTile(
                            title: spaceName,
                            isSelected: isSelected,
                            onTap: () => _selectSpace(space),
                          );
                        }),
                      const SizedBox(height: 32),
                    ],

                    // List Section
                    if (_selectedSpaceId != null) ...[
                      const Text(
                        'Default List',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Tasks will be added to this list',
                        style: TextStyle(
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
                          child: const Center(
                            child: Text(
                              'No lists found in this space',
                              style: TextStyle(
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

                          return _buildSelectionTile(
                            title: listName,
                            isSelected: isSelected,
                            onTap: () => _selectList(list),
                          );
                        }),
                      const SizedBox(height: 32),
                    ],

                    // Disconnect Button
                    GestureDetector(
                      onTap: _disconnectClickUp,
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
                              'Disconnect from ClickUp',
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
