import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;
  final VoidCallback? onBack;

  const DesktopCompleteScreen({super.key, required this.onComplete, this.onBack});

  @override
  State<DesktopCompleteScreen> createState() => _DesktopCompleteScreenState();
}

class _DesktopCompleteScreenState extends State<DesktopCompleteScreen> with TickerProviderStateMixin {
  late AnimationController _confettiController;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _scaleAnimation;
  late Animation<double> _slideAnimation;

  @override
  void initState() {
    super.initState();

    _confettiController = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    );

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    ));

    _scaleAnimation = Tween<double>(
      begin: 0.5,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.elasticOut,
    ));

    _slideAnimation = Tween<double>(
      begin: 50.0,
      end: 0.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    ));

    // Start animations
    Future.delayed(const Duration(milliseconds: 200), () {
      if (mounted) {
        _fadeController.forward();
        _confettiController.forward();
      }
    });
  }

  @override
  void dispose() {
    _confettiController.dispose();
    _fadeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Center(
      child: Container(
        constraints: BoxConstraints(
          maxWidth: responsive.maxContainerWidth(baseMaxWidth: 600),
          maxHeight: responsive.safeAreaHeight,
        ),
        child: SingleChildScrollView(
          child: AnimatedBuilder(
            animation: _fadeController,
            builder: (context, child) {
              return FadeTransition(
                opacity: _fadeAnimation,
                child: Transform.translate(
                  offset: Offset(0, _slideAnimation.value),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Simple minimal success icon matching other pages
                      ScaleTransition(
                        scale: _scaleAnimation,
                        child: Container(
                          width: 56,
                          height: 56,
                          decoration: BoxDecoration(
                            color: const Color(0xFF1A1A1A),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: const Icon(
                            Icons.check_rounded,
                            color: Colors.white,
                            size: 28,
                          ),
                        ),
                      ),

                      const SizedBox(height: 32),

                      // Clean title
                      const Text(
                        'You\'re all set!',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                          letterSpacing: -0.5,
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 8),

                      // Clean subtitle
                      Container(
                        constraints: const BoxConstraints(maxWidth: 480),
                        padding: const EdgeInsets.symmetric(horizontal: 40),
                        child: const Text(
                          'Welcome to Omi! Your AI companion is ready to assist you with conversations, tasks, and more.',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w400,
                            color: Color(0xFF9CA3AF),
                            height: 1.5,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),

                      const SizedBox(height: 48),

                      // Clean button
                      Container(
                        constraints: const BoxConstraints(maxWidth: 400),
                        margin: const EdgeInsets.symmetric(horizontal: 40),
                        child: Container(
                          width: double.infinity,
                          decoration: BoxDecoration(
                            color: const Color(0xFF1A1A1A),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: const Color(0xFF2A2A2A),
                              width: 1,
                            ),
                          ),
                          child: Material(
                            color: Colors.transparent,
                            child: InkWell(
                              borderRadius: BorderRadius.circular(12),
                              onTap: widget.onComplete,
                              child: const Padding(
                                padding: EdgeInsets.symmetric(
                                  horizontal: 24,
                                  vertical: 18,
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Text(
                                      'Start Using Omi',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    SizedBox(width: 8),
                                    Icon(
                                      Icons.arrow_forward_rounded,
                                      color: Colors.white,
                                      size: 20,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),

                      const SizedBox(height: 16),

                      // Small back button
                      if (widget.onBack != null)
                        TextButton(
                          onPressed: widget.onBack,
                          child: const Text(
                            'Back',
                            style: TextStyle(
                              color: Color(0xFF6B7280),
                              fontSize: 13,
                              fontWeight: FontWeight.w400,
                            ),
                          ),
                        ),

                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildFeatureHighlights(ResponsiveHelper responsive) {
    final features = [
      {
        'icon': Icons.chat_bubble_outline,
        'title': 'Smart Conversations',
        'description': 'Natural AI interactions',
      },
      {
        'icon': Icons.psychology,
        'title': 'Memory & Context',
        'description': 'Remembers your preferences',
      },
      {
        'icon': Icons.speed,
        'title': 'Lightning Fast',
        'description': 'Instant responses',
      },
    ];

    if (responsive.isSmallScreen) {
      // Stack vertically on small screens
      return Column(
        children: features
            .map((feature) => Container(
                  margin: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                  child: _buildFeatureCard(
                    icon: feature['icon'] as IconData,
                    title: feature['title'] as String,
                    description: feature['description'] as String,
                    responsive: responsive,
                  ),
                ))
            .toList(),
      );
    } else {
      // Show in row for larger screens
      return Row(
        children: features
            .map((feature) => Expanded(
                  child: Container(
                    margin: EdgeInsets.symmetric(horizontal: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 12)),
                    child: _buildFeatureCard(
                      icon: feature['icon'] as IconData,
                      title: feature['title'] as String,
                      description: feature['description'] as String,
                      responsive: responsive,
                    ),
                  ),
                ))
            .toList(),
      );
    }
  }

  Widget _buildFeatureCard({
    required IconData icon,
    required String title,
    required String description,
    required ResponsiveHelper responsive,
  }) {
    return Container(
      padding: responsive.cardPadding(),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: responsive.iconSize(baseSize: 48, minSize: 36, maxSize: 56),
            height: responsive.iconSize(baseSize: 48, minSize: 36, maxSize: 56),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  const Color(0xFF667EEA).withOpacity(0.2),
                  const Color(0xFF764BA2).withOpacity(0.2),
                ],
              ),
              borderRadius: BorderRadius.circular(responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),
            ),
            child: Icon(
              icon,
              color: const Color(0xFF667EEA),
              size: responsive.iconSize(baseSize: 24, minSize: 18, maxSize: 28),
            ),
          ),
          SizedBox(height: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),
          Text(
            title,
            style: responsive.responsiveTextStyle(
              baseFontSize: 16,
              minFontSize: 14,
              maxFontSize: 18,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
            textAlign: TextAlign.center,
            overflow: TextOverflow.ellipsis,
            maxLines: 2,
          ),
          SizedBox(height: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10)),
          Text(
            description,
            style: responsive.bodySmall,
            textAlign: TextAlign.center,
            overflow: TextOverflow.ellipsis,
            maxLines: 2,
          ),
        ],
      ),
    );
  }
}
