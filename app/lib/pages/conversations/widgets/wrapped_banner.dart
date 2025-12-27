import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/wrapped_2025_page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class WrappedBanner extends StatefulWidget {
  const WrappedBanner({super.key});

  @override
  State<WrappedBanner> createState() => _WrappedBannerState();
}

class _WrappedBannerState extends State<WrappedBanner> with SingleTickerProviderStateMixin {
  late AnimationController _shimmerController;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Don't show banner if user has already viewed their wrapped
    if (SharedPreferencesUtil().hasViewedWrapped2025) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: GestureDetector(
        onTap: () {
          HapticFeedback.mediumImpact();
          MixpanelManager().wrappedBannerClicked();
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => const Wrapped2025Page(),
            ),
          );
        },
        child: AnimatedBuilder(
          animation: _shimmerController,
          builder: (context, child) {
            return Container(
              height: 80,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(24),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: const [
                    Color(0xFF2E2440), // Muted deep purple
                    Color(0xFF3D2F52), // Soft violet
                    Color(0xFF4A3860), // Gentle purple
                    Color(0xFF382D4A), // Dark purple
                  ],
                  stops: [
                    0.0,
                    0.3 + 0.1 * math.sin(_shimmerController.value * 2 * math.pi),
                    0.6 + 0.1 * math.cos(_shimmerController.value * 2 * math.pi),
                    1.0,
                  ],
                ),
                border: Border.all(
                  color: const Color(0xFF6B5580).withValues(alpha: 0.3),
                  width: 1,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF5B4B78).withValues(alpha: 0.2),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Stack(
                children: [
                  // Sparkle decorations
                  Positioned(
                    top: 12,
                    left: 20,
                    child: _buildSparkle(8, _shimmerController.value),
                  ),
                  Positioned(
                    top: 20,
                    right: 60,
                    child: _buildSparkle(6, _shimmerController.value + 0.3),
                  ),
                  Positioned(
                    bottom: 15,
                    left: 80,
                    child: _buildSparkle(5, _shimmerController.value + 0.6),
                  ),
                  Positioned(
                    bottom: 20,
                    right: 100,
                    child: _buildSparkle(7, _shimmerController.value + 0.5),
                  ),
                  // Content
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Row(
                      children: [
                        // Left side - text
                        Expanded(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  const Text(
                                    '✨',
                                    style: TextStyle(fontSize: 18),
                                  ),
                                  const SizedBox(width: 8),
                                  const Text(
                                    'Your 2025 Wrapped',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                      letterSpacing: -0.3,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'See your year in review',
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.6),
                                  fontSize: 13,
                                  fontWeight: FontWeight.w400,
                                ),
                              ),
                            ],
                          ),
                        ),
                        // Right side - arrow
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(
                            Icons.arrow_forward_rounded,
                            color: Colors.white,
                            size: 20,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildSparkle(double size, double animValue) {
    final opacity = 0.2 + 0.4 * ((math.sin(animValue * 2 * math.pi) + 1) / 2);
    final scale = 0.8 + 0.3 * ((math.sin(animValue * 2 * math.pi) + 1) / 2);
    return Transform.scale(
      scale: scale,
      child: Opacity(
        opacity: opacity,
        child: Icon(
          Icons.star,
          size: size,
          color: const Color(0xFFA794C4),
        ),
      ),
    );
  }
}
