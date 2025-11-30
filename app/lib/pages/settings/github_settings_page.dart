import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/services/github_service.dart';

class GitHubSettingsPage extends StatefulWidget {
  const GitHubSettingsPage({super.key});

  @override
  State<GitHubSettingsPage> createState() => _GitHubSettingsPageState();
}

class _GitHubSettingsPageState extends State<GitHubSettingsPage> {
  final GitHubService _githubService = GitHubService();
  List<GitHubRepository> _repositories = [];
  bool _isLoadingRepos = true;
  String? _selectedRepoFullName;

  @override
  void initState() {
    super.initState();
    _initializeGitHub();
  }

  Future<void> _initializeGitHub() async {
    await _loadRepositories();
    await _loadSavedDefaultRepo();
  }

  Future<void> _loadSavedDefaultRepo() async {
    // Get saved default repo from integration
    // We'll need to get this from the backend integration data
    // For now, we'll load it when we fetch repos
    // Note: We'd need to extend IntegrationResponse to include default_repo
  }

  Future<void> _loadRepositories() async {
    setState(() => _isLoadingRepos = true);

    try {
      final repos = await getGitHubRepositories();

      if (!mounted) return;

      // Try to get saved default repo from integration
      // We'll need to fetch the integration to get default_repo
      final integration = await getIntegration('github');
      String? savedRepo;
      if (integration != null && integration.connected) {
        // Note: We'd need to extend IntegrationResponse to include default_repo
        // For now, we'll just use the first repo or let user select
      }

      setState(() {
        _repositories = repos;
        _isLoadingRepos = false;
        _selectedRepoFullName = savedRepo;
        if (_selectedRepoFullName == null && repos.isNotEmpty) {
          // If no saved repo, don't auto-select - let user choose
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoadingRepos = false;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to load repositories: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _selectRepository(GitHubRepository repo) async {
    final repoFullName = repo.fullName;

    setState(() {
      _selectedRepoFullName = repoFullName;
    });

    // Save to backend
    final success = await setGitHubDefaultRepo(repoFullName);
    if (!mounted) return;

    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Default repository saved'),
          duration: Duration(seconds: 2),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Failed to save default repository'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingRepos) {
      return const Scaffold(
        backgroundColor: Color(0xFF000000),
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return IntegrationSettingsPage(
      appName: 'GitHub',
      appKey: 'github',
      disconnectService: _githubService.disconnect,
      showRefresh: true,
      onRefresh: _initializeGitHub,
      infoText: 'Issues will be created in your default repository',
      children: [
        const Text(
          'Default Repository',
          style: TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Select a default repository for creating issues. You can still specify a different repository when creating issues.',
          style: TextStyle(
            color: Color(0xFF8E8E93),
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 16),
        if (_repositories.isEmpty)
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: Text(
                'No repositories found',
                style: TextStyle(
                  color: Color(0xFF8E8E93),
                  fontSize: 14,
                ),
              ),
            ),
          )
        else
          // List repositories - will be scrollable within IntegrationSettingsPage
          ..._repositories.map((repo) {
            final isSelected = _selectedRepoFullName == repo.fullName;
            return GestureDetector(
              onTap: () => _selectRepository(repo),
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
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            repo.fullName,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              if (repo.isPrivate)
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.orange.withOpacity(0.2),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: const Text(
                                    'Private',
                                    style: TextStyle(
                                      color: Colors.orange,
                                      fontSize: 10,
                                    ),
                                  ),
                                ),
                              if (repo.isPrivate) const SizedBox(width: 8),
                              Text(
                                'Updated ${_formatDate(repo.updatedAt)}',
                                style: const TextStyle(
                                  color: Color(0xFF8E8E93),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ],
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
    );
  }

  String _formatDate(String dateStr) {
    try {
      final date = DateTime.parse(dateStr);
      final now = DateTime.now();
      final difference = now.difference(date);

      if (difference.inDays == 0) {
        return 'today';
      } else if (difference.inDays == 1) {
        return 'yesterday';
      } else if (difference.inDays < 7) {
        return '${difference.inDays} days ago';
      } else if (difference.inDays < 30) {
        final weeks = (difference.inDays / 7).floor();
        return weeks == 1 ? '1 week ago' : '$weeks weeks ago';
      } else {
        final months = (difference.inDays / 30).floor();
        return months == 1 ? '1 month ago' : '$months months ago';
      }
    } catch (e) {
      return dateStr;
    }
  }
}
