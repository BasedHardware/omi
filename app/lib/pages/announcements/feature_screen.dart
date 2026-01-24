import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';

import 'package:omi/models/announcement.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class FeatureScreen extends StatefulWidget {
  final Announcement feature;
  final VoidCallback? onComplete;

  const FeatureScreen({
    super.key,
    required this.feature,
    this.onComplete,
  });

  /// Show the feature screen as a full-screen modal.
  static Future<void> show(BuildContext context, Announcement feature) {
    return Navigator.of(context).push(
      PageRouteBuilder(
        fullscreenDialog: true,
        pageBuilder: (context, animation, secondaryAnimation) => FeatureScreen(feature: feature),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween<Offset>(
                begin: const Offset(0, 0.1),
                end: Offset.zero,
              ).animate(CurvedAnimation(
                parent: animation,
                curve: Curves.easeOut,
              )),
              child: child,
            ),
          );
        },
        transitionDuration: const Duration(milliseconds: 300),
      ),
    );
  }

  @override
  State<FeatureScreen> createState() => _FeatureScreenState();
}

class _FeatureScreenState extends State<FeatureScreen> with SingleTickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _buttonAnimationController;
  int _currentPage = 0;

  FeatureContent get content => widget.feature.featureContent;
  List<FeatureStep> get steps => content.steps;

  // Determine display mode:
  // - Paged mode: Multiple steps where each has its own image/video (swipeable pages)
  // - List mode with header: First step has image, rest are text-only (single scrollable page)
  // - List mode: No steps have images (single scrollable page with numbered list)
  // - Single page: Only one step (with or without image)

  int get _stepsWithMedia => steps.where((step) => step.imageUrl != null || step.videoUrl != null).length;

  // Use paged mode only if multiple steps have their own images
  bool get _usePagedMode => _stepsWithMedia > 1;

  // List mode with header image: first step has image, others don't
  bool get _useListModeWithHeader =>
      steps.length > 1 && _stepsWithMedia == 1 && (steps.first.imageUrl != null || steps.first.videoUrl != null);

  bool get _showPageIndicators => _usePagedMode;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    _buttonAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _buttonAnimationController.dispose();
    super.dispose();
  }

  void _nextPage() {
    if (_usePagedMode && _currentPage < steps.length - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    } else {
      _complete();
    }
  }

  void _complete() {
    widget.onComplete?.call();
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(child: _buildContent()),
            _buildFooter(),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    // Single step: show single page (with or without image)
    if (steps.length == 1) {
      return _buildStepPage(steps.first);
    }

    // List mode with header image: first step has image, rest are text-only
    if (_useListModeWithHeader) {
      return _buildListModeWithHeader();
    }

    // Paged mode: multiple steps with their own images (swipeable)
    if (_usePagedMode) {
      return PageView.builder(
        controller: _pageController,
        itemCount: steps.length,
        onPageChanged: (index) {
          setState(() => _currentPage = index);
        },
        itemBuilder: (context, index) {
          return _buildStepPage(steps[index]);
        },
      );
    }

    // List mode: no images, all steps as numbered list
    return _buildListMode();
  }

  /// List mode with header - shows image at top, then all steps as a list below
  Widget _buildListModeWithHeader() {
    final firstStep = steps.first;

    return LayoutBuilder(
      builder: (context, constraints) {
        final imageHeight = (constraints.maxHeight * 0.35).clamp(160.0, 240.0);

        return SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 16),
              // Header image
              if (firstStep.imageUrl != null) _buildImage(firstStep.imageUrl!, imageHeight),
              if (firstStep.videoUrl != null) _buildVideoPlaceholder(firstStep.videoUrl!, imageHeight),
              const SizedBox(height: 24),
              // Main title centered
              Center(
                child: Text(
                  content.title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 24,
                    fontWeight: FontWeight.w700,
                    height: 1.25,
                    letterSpacing: -0.5,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 24),
              // List of all steps (including first one as text)
              for (int i = 0; i < steps.length; i++) ...[
                _buildListItem(steps[i], i + 1),
                if (i < steps.length - 1) const SizedBox(height: 20),
              ],
              const SizedBox(height: 24),
            ],
          ),
        );
      },
    );
  }

  /// List mode - shows all steps vertically on one scrollable page (no images)
  Widget _buildListMode() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 24),
          // Main title centered
          Center(
            child: Text(
              content.title,
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 24,
                fontWeight: FontWeight.w700,
                height: 1.25,
                letterSpacing: -0.5,
              ),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: 32),
          // List of steps
          for (int i = 0; i < steps.length; i++) ...[
            _buildListItem(steps[i], i + 1),
            if (i < steps.length - 1) const SizedBox(height: 24),
          ],
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  /// A single item in list mode (numbered step)
  Widget _buildListItem(FeatureStep step, int number) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Number badge
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Center(
            child: Text(
              '$number',
              style: const TextStyle(
                color: ResponsiveHelper.purplePrimary,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
        const SizedBox(width: 14),
        // Content
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                step.title,
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 17,
                  fontWeight: FontWeight.w600,
                  height: 1.3,
                ),
              ),
              const SizedBox(height: 6),
              _buildListDescription(step),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildListDescription(FeatureStep step) {
    final description = step.description;
    final highlightText = step.highlightText;

    if (highlightText != null && description.contains(highlightText)) {
      final parts = description.split(highlightText);
      return RichText(
        text: TextSpan(
          style: const TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 15,
            height: 1.5,
          ),
          children: [
            TextSpan(text: parts.first),
            TextSpan(
              text: highlightText,
              style: TextStyle(
                color: ResponsiveHelper.purplePrimary,
                fontWeight: FontWeight.w600,
                backgroundColor: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
              ),
            ),
            if (parts.length > 1) TextSpan(text: parts.sublist(1).join(highlightText)),
          ],
        ),
      );
    }

    return Text(
      description,
      style: const TextStyle(
        color: ResponsiveHelper.textSecondary,
        fontSize: 15,
        height: 1.5,
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 12, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Feature title (shows overall feature name)
          Expanded(
            child: Text(
              content.title,
              style: const TextStyle(
                color: ResponsiveHelper.textTertiary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          // Close button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: _complete,
              borderRadius: BorderRadius.circular(20),
              child: Container(
                padding: const EdgeInsets.all(8),
                child: const Icon(
                  Icons.close,
                  color: ResponsiveHelper.textSecondary,
                  size: 24,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStepPage(FeatureStep step) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Calculate image height based on available space
        final availableHeight = constraints.maxHeight;
        final imageHeight = (availableHeight * 0.45).clamp(200.0, 320.0);

        return SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const SizedBox(height: 16),
                // Image or Video with better sizing
                if (step.imageUrl != null) _buildImage(step.imageUrl!, imageHeight),
                if (step.videoUrl != null) _buildVideoPlaceholder(step.videoUrl!, imageHeight),
                if (step.imageUrl != null || step.videoUrl != null) const SizedBox(height: 32),
                // Title with better typography
                Text(
                  step.title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 26,
                    fontWeight: FontWeight.w700,
                    height: 1.25,
                    letterSpacing: -0.5,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 14),
                // Description with optional highlighted text
                _buildDescription(step),
                const SizedBox(height: 32),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildImage(String imageUrl, double height) {
    return Container(
      height: height,
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: CachedNetworkImage(
          imageUrl: imageUrl,
          fit: BoxFit.cover,
          placeholder: (context, url) => Container(
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Center(
              child: CircularProgressIndicator(
                color: Colors.white54,
                strokeWidth: 2,
              ),
            ),
          ),
          errorWidget: (context, url, error) => Container(
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Icon(
              Icons.image_not_supported_outlined,
              color: ResponsiveHelper.textQuaternary,
              size: 48,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildVideoPlaceholder(String videoUrl, double height) {
    return Container(
      height: height,
      width: double.infinity,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Play button
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.2),
                  blurRadius: 12,
                  spreadRadius: 2,
                ),
              ],
            ),
            child: const Icon(
              Icons.play_arrow_rounded,
              color: Colors.black,
              size: 36,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDescription(FeatureStep step) {
    final description = step.description;
    final highlightText = step.highlightText;

    if (highlightText != null && description.contains(highlightText)) {
      final parts = description.split(highlightText);
      return RichText(
        textAlign: TextAlign.center,
        text: TextSpan(
          style: const TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 16,
            height: 1.6,
            letterSpacing: 0.1,
          ),
          children: [
            TextSpan(text: parts.first),
            TextSpan(
              text: highlightText,
              style: TextStyle(
                color: ResponsiveHelper.purplePrimary,
                fontWeight: FontWeight.w600,
                backgroundColor: ResponsiveHelper.purplePrimary.withValues(alpha: 0.15),
              ),
            ),
            if (parts.length > 1) TextSpan(text: parts.sublist(1).join(highlightText)),
          ],
        ),
      );
    }

    return Text(
      description,
      style: const TextStyle(
        color: ResponsiveHelper.textSecondary,
        fontSize: 16,
        height: 1.6,
        letterSpacing: 0.1,
      ),
      textAlign: TextAlign.center,
    );
  }

  Widget _buildFooter() {
    final isLastStep = !_usePagedMode || _currentPage == steps.length - 1;

    return Container(
      padding: EdgeInsets.fromLTRB(24, 16, 24, _showPageIndicators ? 20 : 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Page indicators (only for paged mode with multiple steps)
          if (_showPageIndicators) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: List.generate(
                steps.length,
                (index) => _buildPageDot(index),
              ),
            ),
            const SizedBox(height: 20),
          ],
          // Primary action button with gradient
          _buildActionButton(isLastStep),
        ],
      ),
    );
  }

  Widget _buildActionButton(bool isLastStep) {
    return GestureDetector(
      onTapDown: (_) => _buttonAnimationController.forward(),
      onTapUp: (_) {
        _buttonAnimationController.reverse();
        _nextPage();
      },
      onTapCancel: () => _buttonAnimationController.reverse(),
      child: AnimatedBuilder(
        animation: _buttonAnimationController,
        builder: (context, child) {
          final scale = 1.0 - (_buttonAnimationController.value * 0.03);
          return Transform.scale(
            scale: scale,
            child: Container(
              width: double.infinity,
              height: 56,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.15),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    isLastStep ? 'Got it' : 'Continue',
                    style: const TextStyle(
                      color: Colors.black,
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.3,
                    ),
                  ),
                  if (!isLastStep) ...[
                    const SizedBox(width: 8),
                    const Icon(
                      Icons.arrow_forward_rounded,
                      color: Colors.black,
                      size: 20,
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildPageDot(int index) {
    final isActive = index == _currentPage;
    final isPast = index < _currentPage;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      margin: const EdgeInsets.symmetric(horizontal: 4),
      width: isActive ? 28 : 8,
      height: 8,
      decoration: BoxDecoration(
        color: isActive
            ? Colors.white
            : isPast
                ? Colors.white54
                : ResponsiveHelper.backgroundTertiary,
        borderRadius: BorderRadius.circular(4),
      ),
    );
  }
}
