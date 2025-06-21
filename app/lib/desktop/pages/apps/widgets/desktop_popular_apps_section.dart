import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';

class DesktopPopularAppsSection extends StatelessWidget {
  final List<App> popularApps;

  const DesktopPopularAppsSection({
    super.key,
    required this.popularApps,
  });

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    if (popularApps.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Section header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.star_rounded,
                  color: ResponsiveHelper.purplePrimary,
                  size: 20,
                ),
              ),
              SizedBox(width: responsive.spacing(baseSpacing: 12)),
              Text(
                'Popular Apps',
                style: responsive.titleLarge.copyWith(
                  color: ResponsiveHelper.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),

          SizedBox(height: responsive.spacing(baseSpacing: 20)),

          // Popular apps grid
          _buildPopularAppsGrid(responsive),
        ],
      ),
    );
  }

  Widget _buildPopularAppsGrid(ResponsiveHelper responsive) {
    // Calculate grid dimensions based on screen size
    final crossAxisCount = responsive.isLargeScreen
        ? 4
        : responsive.isMediumScreen
            ? 3
            : 2;
    final displayedApps = popularApps.take(crossAxisCount * 2).toList(); // Show 2 rows max

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        childAspectRatio: 3.2,
        crossAxisSpacing: responsive.spacing(baseSpacing: 16),
        mainAxisSpacing: responsive.spacing(baseSpacing: 12),
      ),
      itemCount: displayedApps.length,
      itemBuilder: (context, index) {
        return _DesktopPopularAppCard(
          app: displayedApps[index],
          responsive: responsive,
        );
      },
    );
  }
}

class _DesktopPopularAppCard extends StatefulWidget {
  final App app;
  final ResponsiveHelper responsive;

  const _DesktopPopularAppCard({
    required this.app,
    required this.responsive,
  });

  @override
  State<_DesktopPopularAppCard> createState() => _DesktopPopularAppCardState();
}

class _DesktopPopularAppCardState extends State<_DesktopPopularAppCard> {
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
            onTap: () => _handleAppTap(),
            borderRadius: BorderRadius.circular(12),
            child: Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: _isHovered
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                      : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                  width: 1,
                ),
                boxShadow: _isHovered
                    ? [
                        BoxShadow(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                          blurRadius: 12,
                          offset: const Offset(0, 4),
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.05),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
              ),
              child: Padding(
                padding: EdgeInsets.all(widget.responsive.spacing(baseSpacing: 16)),
                child: Row(
                  children: [
                    // App icon
                    _buildAppIcon(),

                    SizedBox(width: widget.responsive.spacing(baseSpacing: 12)),

                    // App info
                    Expanded(
                      child: _buildAppInfo(),
                    ),
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
    return CachedNetworkImage(
      imageUrl: widget.app.getImageUrl(),
      httpHeaders: const {
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
      },
      imageBuilder: (context, imageProvider) => Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
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
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.textQuaternary),
            ),
          ),
        ),
      ),
      errorWidget: (context, url, error) => Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Icon(
          Icons.error_outline,
          color: ResponsiveHelper.textQuaternary,
          size: 24,
        ),
      ),
    );
  }

  Widget _buildAppInfo() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        // App name
        Text(
          widget.app.name,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: widget.responsive.labelLarge.copyWith(
            color: ResponsiveHelper.textPrimary,
            fontWeight: FontWeight.w500,
          ),
        ),

        SizedBox(height: widget.responsive.spacing(baseSpacing: 2)),

        // App description
        Text(
          widget.app.description.decodeString,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: widget.responsive.bodySmall.copyWith(
            color: ResponsiveHelper.textTertiary,
            fontSize: 12,
          ),
        ),

        // Rating if available
        if (widget.app.ratingAvg != null) ...[
          SizedBox(height: widget.responsive.spacing(baseSpacing: 4)),
          Row(
            children: [
              const Icon(
                Icons.star_rounded,
                color: ResponsiveHelper.purplePrimary,
                size: 14,
              ),
              const SizedBox(width: 4),
              Text(
                widget.app.getRatingAvg()!,
                style: widget.responsive.bodySmall.copyWith(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  void _handleAppTap() {
    // Navigate to app detail page
    debugPrint('Popular app tapped: ${widget.app.name}');
    // TODO: Implement navigation to app detail page
  }
}
