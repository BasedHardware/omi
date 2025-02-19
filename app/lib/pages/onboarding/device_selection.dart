import 'package:flutter/material.dart';
import 'package:friend_private/backend/auth.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/onboarding/wrapper.dart';
import 'dart:math' as math;

import 'package:friend_private/pages/persona/twitter/social_profile.dart';

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
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Background image
          Image.asset(
            'assets/images/new_background.png',
            fit: BoxFit.cover,
          ),
          Scaffold(
            backgroundColor: Colors.transparent,
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Spacer(),
                    Column(
                      children: [
                        AnimatedBuilder(
                          animation: _controller,
                          builder: (context, child) {
                            return Transform.translate(
                              offset: Offset(0, 10 * math.sin(_controller.value * math.pi)),
                              child: child,
                            );
                          },
                          child: Image.asset(
                            'assets/images/clone.png',
                            width: 240,
                            height: 240,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Text(
                          'omi',
                          style: Theme.of(context).textTheme.displayMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'scale yourself',
                          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                                color: Colors.white.withOpacity(0.8),
                              ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                    const Spacer(),
                    Column(
                      children: [
                        ElevatedButton(
                          onPressed: () {
                            SharedPreferencesUtil().hasOmiDevice = false;
                            signInAnonymously();
                            Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(builder: (context) => const SocialHandleScreen()),
                            );
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.grey[900],
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                            ),
                          ),
                          child: const Text(
                            'Get Started',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                        TextButton(
                          onPressed: () {
                            SharedPreferencesUtil().hasOmiDevice = true;
                            Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(builder: (context) => const OnboardingWrapper()),
                            );
                          },
                          child: Text(
                            'I have Omi Device',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.8),
                            ),
                          ),
                        ),
                        const SizedBox(height: 40),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
