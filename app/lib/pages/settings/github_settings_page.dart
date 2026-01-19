import 'package:flutter/material.dart';

import 'package:shimmer/shimmer.dart';

import 'package:omi/backend/http/api/integrations.dart';
import 'package:omi/pages/settings/integration_settings_page.dart';
import 'package:omi/services/github_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
            content: Text(context.l10n.failedToLoadRepos(e.toString())),
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
        SnackBar(
          content: Text(context.l10n.defaultRepoSaved),
          duration: const Duration(seconds: 2),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.failedToSaveDefaultRepo),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Widget _buildShimmerLoading() {
    return Scaffold(
      backgroundColor: const Color(0xFF000000),
      appBar: AppBar(
        backgroundColor: const Color(0xFF000000),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          context.l10n.appSettings('GitHub'),
          style: const TextStyle(
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
              // Connected status shimmer
              Shimmer.fromColors(
                baseColor: Colors.grey[800]!,
                highlightColor: Colors.grey[600]!,
                child: Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 24),
                  decoration: BoxDecoration(
                    color: Colors.grey[800],
                    borderRadius: BorderRadius.circular(8),
                  ),
                  height: 40,
                ),
              ),
              // Title shimmer
              Shimmer.fromColors(
                baseColor: Colors.grey[800]!,
                highlightColor: Colors.grey[600]!,
                child: Container(
                  width: 200,
                  height: 24,
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    color: Colors.grey[800],
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
              // Description shimmer
              Shimmer.fromColors(
                baseColor: Colors.grey[800]!,
                highlightColor: Colors.grey[600]!,
                child: Container(
                  width: double.infinity,
                  height: 16,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.grey[800],
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
              // Repository list shimmer
              Expanded(
                child: ListView.builder(
                  itemCount: 5,
                  itemBuilder: (context, index) {
                    return Shimmer.fromColors(
                      baseColor: Colors.grey[800]!,
                      highlightColor: Colors.grey[600]!,
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.grey[800],
                          borderRadius: BorderRadius.circular(12),
                        ),
                        height: 80,
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingRepos) {
      return _buildShimmerLoading();
    }

    return IntegrationSettingsPage(
      appName: 'GitHub',
      appKey: 'github',
      disconnectService: _githubService.disconnect,
      showRefresh: true,
      onRefresh: _initializeGitHub,
      infoText: context.l10n.issuesCreatedInRepo,
      children: [
        Text(
          context.l10n.defaultRepository,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          context.l10n.selectDefaultRepoDesc,
          style: const TextStyle(
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
            child: Center(
              child: Text(
                context.l10n.noReposFound,
                style: const TextStyle(
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
                                  child: Text(
                                    context.l10n.private,
                                    style: const TextStyle(
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
