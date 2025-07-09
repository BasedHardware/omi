import 'package:flutter/material.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/wrapper.dart';

import 'package:omi/pages/persona/twitter/social_profile.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';

class DeviceSelectionPage extends StatefulWidget {
  const DeviceSelectionPage({super.key});

  @override
  State<DeviceSelectionPage> createState() => _DeviceSelectionPageState();
}

class _DeviceSelectionPageState extends State<DeviceSelectionPage> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(seconds: 6),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      child: Container(
        decoration: const BoxDecoration(
          image: DecorationImage(
            image: AssetImage('assets/images/onboarding-bg-1.png'),
            fit: BoxFit.cover,
          ),
        ),
        child: Scaffold(
          backgroundColor: Colors.transparent,
          body: Column(
            children: [
              // Background image area - takes remaining space
              Expanded(
                child: Container(), // Just takes up space for background image
              ),

              // Bottom drawer card - wraps content
              Container(
                width: double.infinity,
                padding: EdgeInsets.fromLTRB(32, 48, 32, MediaQuery.of(context).padding.bottom + 8),
                decoration: const BoxDecoration(
                  color: Colors.black,
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(40),
                    topRight: Radius.circular(40),
                  ),
                ),
                child: SafeArea(
                  top: false,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Title and subtitle
                      const Text(
                        'Omi – Your AI Companion',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 32,
                          fontWeight: FontWeight.bold,
                          height: 1.2,
                          fontFamily: 'Manrope',
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Capture every moment. Get AI-powered\nsummaries. Never take notes again.',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.8),
                          fontSize: 16,
                          height: 1.4,
                          fontFamily: 'Manrope',
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 40),

                      // Continue button
                      SizedBox(
                        width: double.infinity,
                        height: 56,
                        child: ElevatedButton(
                          onPressed: () async {
                            await Posthog().capture(
                              eventName: 'clicked_get_started',
                            );
                            routeToPage(context, const OnboardingWrapper());
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: Colors.black,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                            ),
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                'Get Started',
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'Manrope',
                                ),
                              ),
                              SizedBox(width: 8),
                              Icon(Icons.arrow_forward, size: 20),
                            ],
                          ),
                        ),
                      ),

                      const SizedBox(height: 16),

                      // Privacy policy text
                      RichText(
                        textAlign: TextAlign.center,
                        text: TextSpan(
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 12,
                            fontFamily: 'Manrope',
                          ),
                          children: const [
                            TextSpan(text: 'By continuing, you agree to our '),
                            TextSpan(
                              text: 'Privacy Policy',
                              style: TextStyle(
                                decoration: TextDecoration.underline,
                              ),
                            ),
                            TextSpan(text: ' & '),
                            TextSpan(
                              text: 'Terms of Use',
                              style: TextStyle(
                                decoration: TextDecoration.underline,
                              ),
                            ),
                            TextSpan(text: '.'),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
