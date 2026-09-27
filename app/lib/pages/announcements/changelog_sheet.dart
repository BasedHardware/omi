import 'package:flutter/material.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/ui/ui.dart';

class ChangelogSheet extends StatefulWidget {
  final List<Announcement>? changelogs;
  final Future<List<Announcement>> Function()? changelogsFuture;

  const ChangelogSheet({super.key, this.changelogs, this.changelogsFuture})
      : assert(changelogs != null || changelogsFuture != null);

  /// Show the changelog sheet as a modal bottom sheet with pre-loaded data.
  static Future<void> show(BuildContext context, List<Announcement> changelogs) {
    if (changelogs.isEmpty) return Future.value();

    return showOmiSheet(
      context: context,
      showCloseButton: false,
      padding: EdgeInsets.zero,
      builder: (context) => ChangelogSheet(changelogs: changelogs),
    );
  }

  static Future<void> showWithLoading(BuildContext context, Future<List<Announcement>> Function() fetchChangelogs) {
    return showOmiSheet(
      context: context,
      showCloseButton: false,
      padding: EdgeInsets.zero,
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
  bool _failed = false;

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
          _failed = true;
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
    // The sheet shell (showOmiSheet) owns the surface, corners and drag handle; the title changes
    // with the version on screen, so the header row lives here.
    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.75,
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: _isLoading
                ? _buildLoadingState()
                : _failed
                    ? OmiErrorState(
                        message: context.l10n.couldNotLoadWhatsNew,
                        onRetry: () {
                          setState(() {
                            _isLoading = true;
                            _failed = false;
                          });
                          return _loadChangelogs();
                        },
                      )
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
          if (!_isLoading && !_failed) _buildFooter(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    String title = context.l10n.whatsNew;
    if (!_isLoading && _orderedChangelogs.isNotEmpty) {
      final version = _orderedChangelogs[_currentPage].appVersion ?? '';
      title = context.l10n.whatsNewInVersion(version);
    }

    return Container(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.xxs, OmiSpacing.xxs),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: OmiColors.surface2, width: 1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _isLoading
              ? ShimmerWithTimeout(
                  baseColor: OmiColors.surface2,
                  highlightColor: OmiColors.surface1,
                  child: Container(
                    width: 180,
                    height: 22,
                    decoration: const BoxDecoration(
                      color: OmiColors.surface2,
                      borderRadius: OmiRadius.smAll,
                    ),
                  ),
                )
              : Expanded(child: Semantics(header: true, child: Text(title, style: OmiType.headline))),
          const OmiCloseButton(color: OmiColors.textSecondary),
        ],
      ),
    );
  }

  Widget _buildLoadingState() {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface1,
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
                    decoration: const BoxDecoration(
                      color: OmiColors.surface2,
                      borderRadius: OmiRadius.smAll,
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Title placeholder
                  Expanded(
                    child: Container(
                      height: 20,
                      decoration: const BoxDecoration(
                        color: OmiColors.surface2,
                        borderRadius: OmiRadius.smAll,
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
                      decoration: const BoxDecoration(
                        color: OmiColors.surface2,
                        borderRadius: OmiRadius.smAll,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      height: 14,
                      width: MediaQuery.of(context).size.width * 0.6,
                      decoration: const BoxDecoration(
                        color: OmiColors.surface2,
                        borderRadius: OmiRadius.smAll,
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
            ExcludeSemantics(child: Text(item.icon ?? '✨', style: OmiType.title3)),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                item.title,
                style: OmiType.headline.copyWith(height: 1.3),
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
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
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
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.md),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: OmiColors.surface2, width: 1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Left arrow - go to older version (lower index)
          _buildNavigationButton(
            icon: Icons.chevron_left,
            label: MaterialLocalizations.of(context).previousPageTooltip,
            enabled: _currentPage > 0,
            onTap: () {
              _pageController.previousPage(duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
            },
          ),
          // Version indicator and page dots
          Column(
            children: [
              Text(
                context.l10n.versionLabel(_orderedChangelogs[_currentPage].appVersion ?? ''),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(_orderedChangelogs.length, (index) => _buildPageDot(index)),
              ),
            ],
          ),
          // Right arrow - go to newer version (higher index)
          _buildNavigationButton(
            icon: Icons.chevron_right,
            label: MaterialLocalizations.of(context).nextPageTooltip,
            enabled: _currentPage < _orderedChangelogs.length - 1,
            onTap: () {
              _pageController.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildNavigationButton({
    required IconData icon,
    required String label,
    required bool enabled,
    required VoidCallback onTap,
  }) {
    return OmiIconButton.filled(
      icon: Icon(icon, size: 24),
      label: label,
      diameter: kOmiMinTapTarget,
      fillColor: OmiColors.surface2,
      onPressed: enabled ? onTap : null,
    );
  }

  Widget _buildPageDot(int index) {
    final isActive = index == _currentPage;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 3),
      width: isActive ? 20 : 6,
      height: 6,
      decoration: BoxDecoration(
        color: isActive ? OmiColors.textPrimary : OmiColors.textTertiary,
        borderRadius: OmiRadius.pillAll,
      ),
    );
  }
}
