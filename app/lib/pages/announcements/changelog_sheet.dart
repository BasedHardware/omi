import 'package:flutter/material.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class ChangelogSheet extends StatefulWidget {
  final List<Announcement>? changelogs;
  final Future<List<Announcement>> Function()? changelogsFuture;

  const ChangelogSheet({
    super.key,
    this.changelogs,
    this.changelogsFuture,
  }) : assert(changelogs != null || changelogsFuture != null);

  /// Show the changelog sheet as a modal bottom sheet with pre-loaded data.
  static Future<void> show(BuildContext context, List<Announcement> changelogs) {
    if (changelogs.isEmpty) return Future.value();

    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ChangelogSheet(changelogs: changelogs),
    );
  }

  static Future<void> showWithLoading(
    BuildContext context,
    Future<List<Announcement>> Function() fetchChangelogs,
  ) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ChangelogSheet(changelogsFuture: fetchChangelogs),
    );
  }

  @override
  State<ChangelogSheet> createState() => _ChangelogSheetState();
}

class _ChangelogSheetState extends State<ChangelogSheet> {
  late PageController _pageController;
  int _currentPage = 0;
  List<Announcement> _orderedChangelogs = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();

    if (widget.changelogs != null) {
      _initializeWithChangelogs(widget.changelogs!);
    } else if (widget.changelogsFuture != null) {
      _loadChangelogs();
    }
  }

  void _initializeWithChangelogs(List<Announcement> changelogs) {
    // Reverse so oldest is at index 0, newest at the end
    _orderedChangelogs = changelogs.reversed.toList();
    // Start on the last page (latest version)
    _currentPage = _orderedChangelogs.isEmpty ? 0 : _orderedChangelogs.length - 1;
    _pageController = PageController(initialPage: _currentPage);
    _isLoading = false;
  }

  Future<void> _loadChangelogs() async {
    try {
      final changelogs = await widget.changelogsFuture!();
      if (changelogs.isEmpty) {
        if (mounted) {
          Navigator.pop(context);
        }
        return;
      }
      if (mounted) {
        setState(() {
          _initializeWithChangelogs(changelogs);
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Failed to load changelogs';
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;

    return Container(
      height: screenHeight * 0.75,
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: _isLoading
                ? _buildLoadingState()
                : _error != null
                    ? _buildErrorState()
                    : PageView.builder(
                        controller: _pageController,
                        itemCount: _orderedChangelogs.length,
                        onPageChanged: (index) {
                          setState(() => _currentPage = index);
                        },
                        itemBuilder: (context, index) {
                          return _buildChangelogPage(_orderedChangelogs[index]);
                        },
                      ),
          ),
          if (!_isLoading && _error == null) _buildFooter(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    String title = "What's New";
    if (!_isLoading && _orderedChangelogs.isNotEmpty) {
      final version = _orderedChangelogs[_currentPage].appVersion ?? '';
      title = "What's New in $version";
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 12, 12),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: ResponsiveHelper.backgroundTertiary, width: 1),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _isLoading
              ? ShimmerWithTimeout(
                  baseColor: ResponsiveHelper.backgroundTertiary,
                  highlightColor: ResponsiveHelper.backgroundSecondary,
                  child: Container(
                    width: 180,
                    height: 22,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                )
              : Text(
                  title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
          IconButton(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(
              Icons.close,
              color: ResponsiveHelper.textSecondary,
              size: 24,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingState() {
    return ShimmerWithTimeout(
      baseColor: ResponsiveHelper.backgroundTertiary,
      highlightColor: ResponsiveHelper.backgroundSecondary,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Shimmer for 3 changelog items
            for (int i = 0; i < 3; i++) ...[
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Icon placeholder
                  Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundTertiary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Title placeholder
                  Expanded(
                    child: Container(
                      height: 20,
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              // Description placeholder
              Padding(
                padding: const EdgeInsets.only(left: 36),
                child: Column(
                  children: [
                    Container(
                      height: 14,
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      height: 14,
                      width: MediaQuery.of(context).size.width * 0.6,
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.backgroundTertiary,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ],
                ),
              ),
              if (i < 2) const SizedBox(height: 32),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.error_outline,
            color: Colors.grey.shade500,
            size: 48,
          ),
          const SizedBox(height: 16),
          Text(
            _error ?? 'Something went wrong',
            style: TextStyle(
              color: Colors.grey.shade400,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 16),
          TextButton(
            onPressed: () {
              setState(() {
                _isLoading = true;
                _error = null;
              });
              _loadChangelogs();
            },
            child: Text(AppLocalizations.of(context)!.retry),
          ),
        ],
      ),
    );
  }

  Widget _buildChangelogPage(Announcement changelog) {
    final content = changelog.changelogContent;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (int i = 0; i < content.changes.length; i++) ...[
            _buildChangeItem(content.changes[i]),
            if (i < content.changes.length - 1) const SizedBox(height: 24),
          ],
        ],
      ),
    );
  }

  Widget _buildChangeItem(ChangelogItem item) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Title row with emoji icon
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              item.icon ?? '✨',
              style: const TextStyle(fontSize: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                item.title,
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                  height: 1.3,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        // Description
        Padding(
          padding: const EdgeInsets.only(left: 32),
          child: Text(
            item.description,
            style: const TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 15,
              height: 1.5,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildFooter() {
    if (_orderedChangelogs.length <= 1) {
      return const SizedBox(height: 24);
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: ResponsiveHelper.backgroundTertiary, width: 1),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Left arrow - go to older version (lower index)
          _buildNavigationButton(
            icon: Icons.chevron_left,
            enabled: _currentPage > 0,
            onTap: () {
              _pageController.previousPage(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
              );
            },
          ),
          // Version indicator and page dots
          Column(
            children: [
              Text(
                'Version ${_orderedChangelogs[_currentPage].appVersion ?? ''}',
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(
                  _orderedChangelogs.length,
                  (index) => _buildPageDot(index),
                ),
              ),
            ],
          ),
          // Right arrow - go to newer version (higher index)
          _buildNavigationButton(
            icon: Icons.chevron_right,
            enabled: _currentPage < _orderedChangelogs.length - 1,
            onTap: () {
              _pageController.nextPage(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildNavigationButton({
    required IconData icon,
    required bool enabled,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: enabled ? const Color(0xFF2A2A2E) : ResponsiveHelper.backgroundTertiary,
          shape: BoxShape.circle,
        ),
        child: Icon(
          icon,
          color: enabled ? ResponsiveHelper.textPrimary : ResponsiveHelper.textQuaternary,
          size: 24,
        ),
      ),
    );
  }

  Widget _buildPageDot(int index) {
    final isActive = index == _currentPage;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 3),
      width: isActive ? 20 : 6,
      height: 6,
      decoration: BoxDecoration(
        color: isActive ? ResponsiveHelper.textPrimary : ResponsiveHelper.textQuaternary,
        borderRadius: BorderRadius.circular(3),
      ),
    );
  }
}
