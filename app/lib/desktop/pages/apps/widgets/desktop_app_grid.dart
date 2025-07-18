import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/ui/atoms/omi_badge.dart';
import 'package:omi/ui/atoms/omi_load_more_button.dart';

class DesktopAppGrid extends StatefulWidget {
  final List<App> apps;
  final Function(App) onAppTap;

  const DesktopAppGrid({
    super.key,
    required this.apps,
    required this.onAppTap,
  });

  @override
  State<DesktopAppGrid> createState() => _DesktopAppGridState();
}

class _DesktopAppGridState extends State<DesktopAppGrid> {
  late ScrollController _scrollController;
  static const int _itemsPerPage = 60;
  int _currentPage = 1;
  bool _isLoadingMore = false;

  @override
  void initState() {
    super.initState();
    _scrollController = ScrollController();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      _loadMoreApps();
    }
  }

  void _loadMoreApps() {
    if (_isLoadingMore) return;

    final totalItems = _currentPage * _itemsPerPage;
    if (totalItems >= widget.apps.length) return;

    setState(() {
      _isLoadingMore = true;
    });

    // Simulate loading delay to avoid UI freezing
    Future.delayed(const Duration(milliseconds: 100), () {
      if (mounted) {
        setState(() {
          _currentPage++;
          _isLoadingMore = false;
        });
      }
    });
  }

  List<App> get _displayedApps {
    final totalItems = _currentPage * _itemsPerPage;
    return widget.apps.take(totalItems).toList();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    if (widget.apps.isEmpty) {
      return const SizedBox.shrink();
    }

    // Responsive grid calculation - adapts to screen size
    int crossAxisCount;
    double childAspectRatio;

    if (responsive.screenWidth > 1600) {
      crossAxisCount = 5;
      childAspectRatio = 0.75;
    } else if (responsive.screenWidth > 1200) {
      crossAxisCount = 4;
      childAspectRatio = 0.8;
    } else if (responsive.screenWidth > 900) {
      crossAxisCount = 3;
      childAspectRatio = 0.85;
    } else {
      crossAxisCount = 2;
      childAspectRatio = 0.9;
    }

    return Column(
      children: [
        // Main grid with pagination
        GridView.builder(
          controller: _scrollController,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(), // Handled by parent scroll
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: crossAxisCount,
            childAspectRatio: childAspectRatio,
            crossAxisSpacing: responsive.spacing(baseSpacing: 20),
            mainAxisSpacing: responsive.spacing(baseSpacing: 20),
          ),
          itemCount: _displayedApps.length,
          itemBuilder: (context, index) {
            return _DesktopAppCard(
              key: ValueKey(_displayedApps[index].id), // Optimize rebuilds
              app: _displayedApps[index],
              responsive: responsive,
              onTap: () => widget.onAppTap(_displayedApps[index]),
            );
          },
        ),

        // Loading indicator and load more
        if (_displayedApps.length < widget.apps.length) ...[
          SizedBox(height: responsive.spacing(baseSpacing: 24)),
          _buildLoadMoreSection(responsive),
        ],
      ],
    );
  }

  Widget _buildLoadMoreSection(ResponsiveHelper responsive) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
        child: OmiLoadMoreButton(
          remaining: widget.apps.length - _displayedApps.length,
          loading: _isLoadingMore,
          onPressed: _loadMoreApps,
        ),
      ),
    );
  }
}

class _DesktopAppCard extends StatefulWidget {
  final App app;
  final ResponsiveHelper responsive;
  final VoidCallback onTap;

  const _DesktopAppCard({
    super.key,
    required this.app,
    required this.responsive,
    required this.onTap,
  });

  @override
  State<_DesktopAppCard> createState() => _DesktopAppCardState();
}

class _DesktopAppCardState extends State<_DesktopAppCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOutCubic,
        transform: Matrix4.identity()..scale(_isHovered ? 1.02 : 1.0),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.onTap,
            borderRadius: BorderRadius.circular(16),
            child: Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: _isHovered
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                      : ResponsiveHelper.backgroundTertiary.withOpacity(0.2),
                  width: 1,
                ),
                boxShadow: _isHovered
                    ? [
                        BoxShadow(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.04),
                          blurRadius: 20,
                          offset: const Offset(0, 8),
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.03),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
              ),
              child: Padding(
                padding: EdgeInsets.all(widget.responsive.spacing(baseSpacing: 20)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        _buildAppIcon(),
                        const Spacer(),
                      ],
                    ),
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          vertical: widget.responsive.spacing(baseSpacing: 12),
                        ),
                        child: _buildAppInfo(),
                      ),
                    ),
                    _buildBottomSection(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAppIcon() {
    final iconSize = widget.responsive.responsiveWidth(
      baseWidth: 56,
      minWidth: 48,
      maxWidth: 64,
    );

    return CachedNetworkImage(
      imageUrl: widget.app.getImageUrl(),
      httpHeaders: const {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
      },
      imageBuilder: (context, imageProvider) => Container(
        width: iconSize,
        height: iconSize,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          image: DecorationImage(
            image: imageProvider,
            fit: BoxFit.cover,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.1),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
      ),
      placeholder: (context, url) => Container(
        width: iconSize,
        height: iconSize,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Center(
          child: SizedBox(
            width: iconSize * 0.4,
            height: iconSize * 0.4,
            child: const CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.textQuaternary),
            ),
          ),
        ),
      ),
      errorWidget: (context, url, error) => Container(
        width: iconSize,
        height: iconSize,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Icon(
          Icons.apps,
          color: ResponsiveHelper.textQuaternary,
          size: iconSize * 0.5,
        ),
      ),
      memCacheHeight: (iconSize * 2).toInt(),
      memCacheWidth: (iconSize * 2).toInt(),
    );
  }

  Widget _buildInstalledBadge() => const OmiBadge(label: 'Installed');

  Widget _buildAppInfo() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.app.name,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: widget.responsive
              .responsiveTextStyle(
                baseFontSize: 16,
                minFontSize: 14,
                maxFontSize: 18,
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.textPrimary,
              )
              .copyWith(height: 1.2),
        ),

        SizedBox(height: widget.responsive.spacing(baseSpacing: 8)),

        // App description - flexible
        Expanded(
          child: Text(
            widget.app.description.decodeString,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: widget.responsive
                .responsiveTextStyle(
                  baseFontSize: 13,
                  minFontSize: 12,
                  maxFontSize: 14,
                  color: ResponsiveHelper.textTertiary,
                )
                .copyWith(height: 1.4),
          ),
        ),
      ],
    );
  }

  Widget _buildBottomSection() {
    return Row(
      children: [
        if (widget.app.ratingAvg != null) ...[
          Icon(
            Icons.star_rounded,
            color: ResponsiveHelper.purplePrimary,
            size: widget.responsive.responsiveWidth(baseWidth: 16, minWidth: 14, maxWidth: 18),
          ),
          SizedBox(width: widget.responsive.spacing(baseSpacing: 4)),
          Text(
            widget.app.getRatingAvg()!,
            style: widget.responsive.responsiveTextStyle(
              baseFontSize: 12,
              minFontSize: 11,
              maxFontSize: 13,
              fontWeight: FontWeight.w500,
              color: ResponsiveHelper.textSecondary,
            ),
          ),
          const Spacer(),
        ] else
          const Spacer(),
        _buildActionButton(),
      ],
    );
  }

  Widget _buildActionButton() {
    final isInstalled = widget.app.enabled;

    if (isInstalled) {
      return _buildInstalledBadge();
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: widget.responsive.spacing(baseSpacing: 12),
          vertical: widget.responsive.spacing(baseSpacing: 6),
        ),
        decoration: BoxDecoration(
          color: ResponsiveHelper.purplePrimary.withOpacity(_isHovered ? 0.8 : 0.6),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          'Install',
          style: widget.responsive.responsiveTextStyle(
            baseFontSize: 11,
            minFontSize: 10,
            maxFontSize: 12,
            fontWeight: FontWeight.w500,
            color: ResponsiveHelper.textPrimary,
          ),
        ),
      ),
    );
  }
}
