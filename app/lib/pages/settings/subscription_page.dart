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
  late AnimationController _arrowController;
  late Animation<double> _arrowAnimation;

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

    _arrowController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(
      parent: _arrowController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _waveController.dispose();
    _notesController.dispose();
    _arrowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [
            Colors.deepPurple.withOpacity(0.3),
            Colors.deepPurple.withOpacity(0.15),
            Colors.black.withOpacity(0.8),
            Colors.black,
          ],
          stops: const [0.0, 0.2, 0.6, 1.0],
        ),
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          backgroundColor: Colors.black,
          elevation: 0,
          leading: Container(
            margin: const EdgeInsets.all(8),
            child: GestureDetector(
              onTap: () => Navigator.pop(context),
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.close,
                  color: Colors.white,
                  size: 20,
                ),
              ),
            ),
          ),
          title: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              const FaIcon(
                FontAwesomeIcons.crown,
                color: Colors.yellow,
                size: 20,
              ),
              const SizedBox(width: 8),
              const Text(
                'Unlimited Access',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          actions: [
            Container(
              margin: const EdgeInsets.all(8),
              child: GestureDetector(
                onTap: () {
                  // Do nothing for now
                },
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    shape: BoxShape.circle,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 3,
                        height: 3,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 3),
                      Container(
                        width: 3,
                        height: 3,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 3),
                      Container(
                        width: 3,
                        height: 3,
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
        body: SafeArea(
          child: SingleChildScrollView(
            child: Column(
              children: [
                const SizedBox(height: 48),

                // Voice to Notes Flow Graphic (full width, no padding)
                SizedBox(
                  height: 150,
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
                                    const double totalWidth =
                                        420.0; // Total width needed for seamless loop (60 bars × 7px each)
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
                                              final heights = [20.0, 32.0, 45.0, 26.0, 52.0, 39.0, 32.0, 45.0];
                                              final height = heights[index % heights.length];

                                              return Container(
                                                width: 4,
                                                height: height,
                                                margin: const EdgeInsets.symmetric(horizontal: 1.5),
                                                decoration: BoxDecoration(
                                                  color: Colors.red.withOpacity(0.7),
                                                  borderRadius: BorderRadius.circular(2),
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
                                              final heights = [20.0, 32.0, 45.0, 26.0, 52.0, 39.0, 32.0, 45.0];
                                              final height = heights[index % heights.length];

                                              return Container(
                                                width: 4,
                                                height: height,
                                                margin: const EdgeInsets.symmetric(horizontal: 1.5),
                                                decoration: BoxDecoration(
                                                  color: Colors.red.withOpacity(0.7),
                                                  borderRadius: BorderRadius.circular(2),
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
                                    const double totalWidth =
                                        440.0; // Exact width: 8 notes × (45px + 10px margin) = 440px
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
                                                width: 45,
                                                height: 55,
                                                margin: const EdgeInsets.symmetric(horizontal: 5),
                                                decoration: BoxDecoration(
                                                  color: Colors.white.withOpacity(0.95),
                                                  borderRadius: BorderRadius.circular(8),
                                                  boxShadow: [
                                                    BoxShadow(
                                                      color: Colors.black.withOpacity(0.15),
                                                      blurRadius: 4,
                                                      offset: const Offset(0, 2),
                                                    ),
                                                  ],
                                                ),
                                                child: Padding(
                                                  padding: const EdgeInsets.all(6),
                                                  child: Column(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      // Title bar
                                                      Container(
                                                        width: 26,
                                                        height: 3,
                                                        decoration: BoxDecoration(
                                                          color: Colors.black,
                                                          borderRadius: BorderRadius.circular(1.5),
                                                        ),
                                                      ),
                                                      const SizedBox(height: 4),
                                                      // Text lines
                                                      ...List.generate(
                                                          5,
                                                          (i) => Container(
                                                                width: i == 4 ? 24 : 35, // Last line shorter
                                                                height: 2,
                                                                margin: const EdgeInsets.symmetric(vertical: 2),
                                                                decoration: BoxDecoration(
                                                                  color: Colors.grey[350],
                                                                  borderRadius: BorderRadius.circular(1),
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
                                                width: 45,
                                                height: 55,
                                                margin: const EdgeInsets.symmetric(horizontal: 5),
                                                decoration: BoxDecoration(
                                                  color: Colors.white.withOpacity(0.95),
                                                  borderRadius: BorderRadius.circular(8),
                                                  boxShadow: [
                                                    BoxShadow(
                                                      color: Colors.black.withOpacity(0.15),
                                                      blurRadius: 4,
                                                      offset: const Offset(0, 2),
                                                    ),
                                                  ],
                                                ),
                                                child: Padding(
                                                  padding: const EdgeInsets.all(6),
                                                  child: Column(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      // Title bar
                                                      Container(
                                                        width: 26,
                                                        height: 3,
                                                        decoration: BoxDecoration(
                                                          color: Colors.black,
                                                          borderRadius: BorderRadius.circular(1.5),
                                                        ),
                                                      ),
                                                      const SizedBox(height: 4),
                                                      // Text lines
                                                      ...List.generate(
                                                          5,
                                                          (i) => Container(
                                                                width: i == 4 ? 24 : 35, // Last line shorter
                                                                height: 2,
                                                                margin: const EdgeInsets.symmetric(vertical: 2),
                                                                decoration: BoxDecoration(
                                                                  color: Colors.grey[350],
                                                                  borderRadius: BorderRadius.circular(1),
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
                        left: (MediaQuery.of(context).size.width - 120) / 2,
                        top: 5, // Center vertically in the 150px container
                        child: Container(
                          width: 120,
                          height: 120,
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
                            faIcon: FontAwesomeIcons.infinity,
                            text: 'Unlimited conversations',
                          ),
                          const SizedBox(height: 16),
                          _buildFeatureItem(
                            faIcon: FontAwesomeIcons.solidComments,
                            text: 'Ask Omi anything about your life',
                          ),
                          const SizedBox(height: 16),
                          _buildFeatureItem(
                            faIcon: FontAwesomeIcons.brain,
                            text: 'Unlock Omi\'s infinite memory',
                          ),
                          // const SizedBox(height: 16),
                          // _buildFeatureItem(
                          //   faIcon: FontAwesomeIcons.clock,
                          //   text: 'Save 6+ hours per week on average',
                          // ),
                        ],
                      ),
                      const SizedBox(height: 48),

                      // Yearly plan
                      _buildPlanOption(
                        isSelected: selectedPlan == 'yearly',
                        saveTag: '2 Months Free',
                        isPopular: true,
                        title: 'Annual Unlimited',
                        subtitle: '12 months / \$199',
                        monthlyPrice: '\$16 /mo',
                        onTap: () {
                          HapticFeedback.lightImpact();
                          setState(() => selectedPlan = 'yearly');
                        },
                      ),
                      const SizedBox(height: 18),

                      // Monthly plan
                      _buildPlanOption(
                        isSelected: selectedPlan == 'monthly',
                        title: 'Monthly Unlimited',
                        subtitle: null, // Remove subtitle
                        monthlyPrice: '\$19 /mo',
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
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Text(
                                'Continue',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(width: 8),
                              AnimatedBuilder(
                                animation: _arrowAnimation,
                                builder: (context, child) {
                                  return Transform.translate(
                                    offset: Offset(_arrowAnimation.value, 0),
                                    child: const Icon(Icons.arrow_forward, size: 20),
                                  );
                                },
                              ),
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
      ),
    );
  }

  Widget _buildFeatureItem({required IconData faIcon, required String text}) {
    return Row(
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: Colors.white,
              width: 1,
            ),
          ),
          child: Center(
            child: FaIcon(
              faIcon,
              color: Colors.white,
              size: 16,
            ),
          ),
        ),
        const SizedBox(width: 12),
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
    String? saveTag,
    bool isPopular = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25), // Use conversation list background
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.transparent,
            width: 2,
          ),
        ),
        child: Column(
          children: [
            // Popular badge only at the top
            if (isPopular) ...[
              Row(
                children: [
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
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      monthlyPrice,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (saveTag != null) ...[
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.green.shade800,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          saveTag,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                    ],
                  ],
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
