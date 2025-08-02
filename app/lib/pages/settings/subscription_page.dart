import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/settings/webview.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class SubscriptionPage extends StatefulWidget {
  const SubscriptionPage({super.key});

  @override
  State<SubscriptionPage> createState() => _SubscriptionPageState();
}

class _SubscriptionPageState extends State<SubscriptionPage> with TickerProviderStateMixin {
  String selectedPlan = 'yearly'; // 'yearly' or 'monthly'
  late AnimationController _waveController;
  late AnimationController _notesController;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(
      duration: const Duration(milliseconds: 6000), // Half speed: 2000ms → 4000ms
      vsync: this,
    )..repeat();

    _notesController = AnimationController(
      duration: const Duration(milliseconds: 18000), // Half speed: 3000ms → 6000ms
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _waveController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            children: [
              // Header and title with padding
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    // Header with close button
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        GestureDetector(
                          onTap: () => Navigator.pop(context),
                          child: const Icon(
                            Icons.close,
                            color: Colors.grey,
                            size: 24,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Main heading
                    const Text(
                      'Unlimited Access',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 32),
                  ],
                ),
              ),

              // Voice to Notes Flow Graphic (full width, no padding)
              SizedBox(
                height: 120,
                width: double.infinity,
                child: Stack(
                  children: [
                    // Background flow - split into exact halves
                    Row(
                      children: [
                        // Left half - Endless Scrolling Waveform (Left to Right)
                        Expanded(
                          flex: 1,
                          child: ClipRect(
                            child: Container(
                              height: 120,
                              child: AnimatedBuilder(
                                animation: _waveController,
                                builder: (context, child) {
                                  // Seamless infinite scroll left-to-right
                                  const double totalWidth = 300.0; // Total width needed for seamless loop
                                  final scrollOffset = (_waveController.value * totalWidth) % totalWidth;
                                  return Stack(
                                    children: [
                                      // First set of bars
                                      Positioned(
                                        left: -totalWidth + scrollOffset,
                                        top: 0,
                                        bottom: 0,
                                        child: Row(
                                          children: List.generate(60, (index) {
                                            final heights = [15.0, 25.0, 35.0, 20.0, 40.0, 30.0, 25.0, 35.0];
                                            final height = heights[index % heights.length];

                                            return Container(
                                              width: 3,
                                              height: height,
                                              margin: const EdgeInsets.symmetric(horizontal: 1),
                                              decoration: BoxDecoration(
                                                color: Colors.red.withOpacity(0.7),
                                                borderRadius: BorderRadius.circular(1),
                                              ),
                                            );
                                          }),
                                        ),
                                      ),
                                      // Second set for seamless loop (starts exactly where first one ends)
                                      Positioned(
                                        left: scrollOffset,
                                        top: 0,
                                        bottom: 0,
                                        child: Row(
                                          children: List.generate(60, (index) {
                                            final heights = [15.0, 25.0, 35.0, 20.0, 40.0, 30.0, 25.0, 35.0];
                                            final height = heights[index % heights.length];

                                            return Container(
                                              width: 3,
                                              height: height,
                                              margin: const EdgeInsets.symmetric(horizontal: 1),
                                              decoration: BoxDecoration(
                                                color: Colors.red.withOpacity(0.7),
                                                borderRadius: BorderRadius.circular(1),
                                              ),
                                            );
                                          }),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ),
                          ),
                        ),

                        // Right half - Endless Scrolling Notes (Left to Right)
                        Expanded(
                          flex: 1,
                          child: ClipRect(
                            child: Container(
                              height: 120,
                              child: AnimatedBuilder(
                                animation: _notesController,
                                builder: (context, child) {
                                  // Seamless infinite scroll left-to-right
                                  const double totalWidth = 344.0; // Exact width: 8 notes × (35px + 8px margin) = 344px
                                  final scrollOffset = (_notesController.value * totalWidth) % totalWidth;
                                  return Stack(
                                    children: [
                                      // First set of notes
                                      Positioned(
                                        left: -totalWidth + scrollOffset,
                                        top: 0,
                                        bottom: 0,
                                        child: Row(
                                          children: List.generate(8, (index) {
                                            return Container(
                                              width: 35,
                                              height: 45,
                                              margin: const EdgeInsets.symmetric(horizontal: 4),
                                              decoration: BoxDecoration(
                                                color: Colors.white.withOpacity(0.95),
                                                borderRadius: BorderRadius.circular(6),
                                                boxShadow: [
                                                  BoxShadow(
                                                    color: Colors.black.withOpacity(0.15),
                                                    blurRadius: 4,
                                                    offset: const Offset(0, 2),
                                                  ),
                                                ],
                                              ),
                                              child: Padding(
                                                padding: const EdgeInsets.all(4),
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    // Title bar
                                                    Container(
                                                      width: 20,
                                                      height: 2.5,
                                                      decoration: BoxDecoration(
                                                        color: Colors.black,
                                                        borderRadius: BorderRadius.circular(1),
                                                      ),
                                                    ),
                                                    const SizedBox(height: 3),
                                                    // Text lines
                                                    ...List.generate(
                                                        5,
                                                        (i) => Container(
                                                              width: i == 4 ? 18 : 27, // Last line shorter
                                                              height: 1.5,
                                                              margin: const EdgeInsets.symmetric(vertical: 1.5),
                                                              decoration: BoxDecoration(
                                                                color: Colors.grey[350],
                                                                borderRadius: BorderRadius.circular(0.5),
                                                              ),
                                                            )),
                                                  ],
                                                ),
                                              ),
                                            );
                                          }),
                                        ),
                                      ),
                                      // Second set for seamless loop (starts exactly where first one ends)
                                      Positioned(
                                        left: scrollOffset,
                                        top: 0,
                                        bottom: 0,
                                        child: Row(
                                          children: List.generate(8, (index) {
                                            return Container(
                                              width: 35,
                                              height: 45,
                                              margin: const EdgeInsets.symmetric(horizontal: 4),
                                              decoration: BoxDecoration(
                                                color: Colors.white.withOpacity(0.95),
                                                borderRadius: BorderRadius.circular(6),
                                                boxShadow: [
                                                  BoxShadow(
                                                    color: Colors.black.withOpacity(0.15),
                                                    blurRadius: 4,
                                                    offset: const Offset(0, 2),
                                                  ),
                                                ],
                                              ),
                                              child: Padding(
                                                padding: const EdgeInsets.all(4),
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    // Title bar
                                                    Container(
                                                      width: 20,
                                                      height: 2.5,
                                                      decoration: BoxDecoration(
                                                        color: Colors.black,
                                                        borderRadius: BorderRadius.circular(1),
                                                      ),
                                                    ),
                                                    const SizedBox(height: 3),
                                                    // Text lines
                                                    ...List.generate(
                                                        5,
                                                        (i) => Container(
                                                              width: i == 4 ? 18 : 27, // Last line shorter
                                                              height: 1.5,
                                                              margin: const EdgeInsets.symmetric(vertical: 1.5),
                                                              decoration: BoxDecoration(
                                                                color: Colors.grey[350],
                                                                borderRadius: BorderRadius.circular(0.5),
                                                              ),
                                                            )),
                                                  ],
                                                ),
                                              ),
                                            );
                                          }),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),

                    // Omi Device - perfectly centered
                    Positioned(
                      left: (MediaQuery.of(context).size.width - 100) / 2,
                      top: (120 - 100) / 2, // Center vertically in the 120px container
                      child: Container(
                        width: 100,
                        height: 100,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.blue.withOpacity(0.4),
                              blurRadius: 20,
                              spreadRadius: 3,
                            ),
                          ],
                        ),
                        child: ClipOval(
                          child: Image.asset(
                            'assets/images/omi-without-rope.png',
                            fit: BoxFit.cover,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Rest of content with padding
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Column(
                  children: [
                    const SizedBox(height: 32),

                    // Features list
                    Column(
                      children: [
                        _buildFeatureItem(
                          icon: Icons.all_inclusive,
                          text: 'Unlimited conversations',
                        ),
                        const SizedBox(height: 16),
                        _buildFeatureItem(
                          icon: Icons.quiz,
                          text: 'Ask Omi anything about your life',
                        ),
                        const SizedBox(height: 16),
                        _buildFeatureItem(
                          icon: Icons.translate,
                          text: 'Unlock Omi\'s infinite memory',
                        ),
                      ],
                    ),
                    const SizedBox(height: 32),

                    // Yearly plan
                    _buildPlanOption(
                      isSelected: selectedPlan == 'yearly',
                      badge: 'SAVE 20%',
                      isPopular: true,
                      title: 'Yearly Plan',
                      subtitle: '12 month / \$199',
                      monthlyPrice: '\$16.58/mo',
                      onTap: () {
                        HapticFeedback.lightImpact();
                        setState(() => selectedPlan = 'yearly');
                      },
                    ),
                    const SizedBox(height: 12),

                    // Monthly plan
                    _buildPlanOption(
                      isSelected: selectedPlan == 'monthly',
                      title: 'Monthly Plan',
                      subtitle: null, // Remove subtitle
                      monthlyPrice: '\$19/mo',
                      onTap: () {
                        HapticFeedback.lightImpact();
                        setState(() => selectedPlan = 'monthly');
                      },
                    ),
                    const SizedBox(height: 24),

                    // Continue button
                    SizedBox(
                      width: double.infinity,
                      height: 56,
                      child: ElevatedButton(
                        onPressed: () {
                          HapticFeedback.mediumImpact();
                          _handleSubscribe();
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: Colors.black,
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              'Continue',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            SizedBox(width: 8),
                            Icon(Icons.arrow_forward, size: 20),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Footer links
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _buildFooterLink('Privacy'),
                        const SizedBox(width: 24),
                        _buildFooterLink('Terms'),
                        const SizedBox(width: 24),
                        _buildFooterLink('Restore'),
                      ],
                    ),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFeatureItem({required IconData icon, required String text}) {
    return Row(
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.2),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            icon,
            color: Colors.white,
            size: 18,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w400,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPlanOption({
    required bool isSelected,
    required String title,
    required String? subtitle,
    required String monthlyPrice,
    required VoidCallback onTap,
    String? badge,
    bool isPopular = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25), // Use conversation list background
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.transparent,
            width: 2,
          ),
        ),
        child: Column(
          children: [
            // Small badges at the top
            if (isPopular || badge != null) ...[
              Row(
                children: [
                  if (isPopular) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Text(
                        'POPULAR',
                        style: TextStyle(
                          color: Colors.black,
                          fontSize: 9,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                    if (badge != null) const SizedBox(width: 8),
                  ],
                  if (badge != null) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: Colors.green,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        badge,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 9,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 12),
            ],
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: Colors.grey[400],
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ],
                ),
                Text(
                  monthlyPrice,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFooterLink(String text) {
    return Text(
      text,
      style: TextStyle(
        color: Colors.grey[500],
        fontSize: 14,
        decoration: TextDecoration.underline,
        decorationColor: Colors.grey[500],
      ),
    );
  }

  void _handleSubscribe() {
    final bool isYearly = selectedPlan == 'yearly';
    final String url = isYearly
        ? 'https://buy.stripe.com/28EbIT9xW0KybwigG66wE1z' // Annual plan
        : 'https://buy.stripe.com/aFaeV5cK8dxk8k6cpQ6wE1y'; // Monthly plan

    MixpanelManager().track('Subscription Selected', properties: {
      'plan_type': isYearly ? 'yearly' : 'monthly',
      'price': isYearly ? 199 : 19,
    });

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => PageWebView(
          url: url,
          title: 'Complete Subscription',
        ),
      ),
    );
  }
}
