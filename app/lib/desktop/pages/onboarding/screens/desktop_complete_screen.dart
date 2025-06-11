import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;

  const DesktopCompleteScreen({super.key, required this.onComplete});

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
                      // Success Icon with animation
                      ScaleTransition(
                        scale: _scaleAnimation,
                        child: Container(
                          width: responsive.iconSize(baseSize: 120, minSize: 80, maxSize: 140),
                          height: responsive.iconSize(baseSize: 120, minSize: 80, maxSize: 140),
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [
                                Color(0xFF4CAF50),
                                Color(0xFF45A049),
                                Color(0xFF66BB6A),
                              ],
                            ),
                            borderRadius: BorderRadius.circular(
                                responsive.spacing(baseSpacing: 30, minSpacing: 20, maxSpacing: 40)),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF4CAF50).withOpacity(0.4),
                                blurRadius: responsive.spacing(baseSpacing: 20, minSpacing: 15, maxSpacing: 25),
                                offset: Offset(0, responsive.spacing(baseSpacing: 10, minSpacing: 8, maxSpacing: 12)),
                              ),
                            ],
                          ),
                          child: Icon(
                            Icons.check,
                            color: Colors.white,
                            size: responsive.iconSize(baseSize: 60, minSize: 40, maxSize: 70),
                          ),
                        ),
                      ),

                      SizedBox(height: responsive.spacing(baseSpacing: 48, minSpacing: 32, maxSpacing: 64)),

                      // Success Title
                      Text(
                        'You\'re all set!',
                        style: responsive.titleLarge,
                        textAlign: TextAlign.center,
                      ),

                      SizedBox(height: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 24)),

                      // Success Subtitle
                      Text(
                        'Welcome to Omi! Your AI companion is ready to assist you with conversations, tasks, and more.',
                        style: responsive.bodyLarge,
                        textAlign: TextAlign.center,
                      ),

                      SizedBox(height: responsive.spacing(baseSpacing: 48, minSpacing: 32, maxSpacing: 64)),

                      // Feature highlights
                      _buildFeatureHighlights(responsive),

                      SizedBox(height: responsive.spacing(baseSpacing: 64, minSpacing: 40, maxSpacing: 80)),

                      // Get Started button
                      Container(
                        width: double.infinity,
                        height: responsive.buttonHeight(),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [
                              Color(0xFF667EEA),
                              Color(0xFF764BA2),
                            ],
                          ),
                          borderRadius: BorderRadius.circular(
                              responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF667EEA).withOpacity(0.3),
                              blurRadius: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16),
                              offset: Offset(0, responsive.spacing(baseSpacing: 4, minSpacing: 3, maxSpacing: 6)),
                            ),
                          ],
                        ),
                        child: Material(
                          color: Colors.transparent,
                          child: InkWell(
                            borderRadius: BorderRadius.circular(
                                responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                            onTap: widget.onComplete,
                            child: Center(
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    'Start Using Omi',
                                    style: responsive.titleMedium,
                                  ),
                                  SizedBox(width: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10)),
                                  Icon(
                                    Icons.arrow_forward,
                                    color: Colors.white,
                                    size: responsive.iconSize(baseSize: 20, minSize: 16, maxSize: 24),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),

                      SizedBox(height: responsive.spacing(baseSpacing: 32, minSpacing: 24, maxSpacing: 40)),

                      // Additional info
                      Container(
                        padding: responsive.cardPadding(),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.05),
                          borderRadius: BorderRadius.circular(
                              responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                          border: Border.all(
                            color: Colors.white.withOpacity(0.1),
                            width: 1,
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              Icons.info_outline,
                              color: const Color(0xFF667EEA),
                              size: responsive.iconSize(baseSize: 24, minSize: 20, maxSize: 28),
                            ),
                            SizedBox(width: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),
                            Expanded(
                              child: Text(
                                'You can always change your preferences later in the settings.',
                                style: responsive.bodySmall,
                              ),
                            ),
                          ],
                        ),
                      ),
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
                    margin: EdgeInsets.symmetric(
                        horizontal: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 12)),
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
