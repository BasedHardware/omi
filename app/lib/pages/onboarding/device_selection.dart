import 'package:flutter/material.dart';
import 'package:friend_private/gen/assets.gen.dart';

import 'package:friend_private/pages/persona/twitter/social_profile.dart';
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
            Assets.images.newBackground.path,
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
                    const Spacer(flex: 6),
                    Column(
                      children: [
                        const SizedBox(height: 10),
                        Container(
                          child: const Text(
                            'omi',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 84,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.5,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),
                        Text(
                          'scale yourself',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 22,
                            fontWeight: FontWeight.w500,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                    const Spacer(flex: 5),
                    const SizedBox(
                      height: 30,
                    ),
                    Column(
                      children: [
                        ElevatedButton(
                          onPressed: () async {
                            await Posthog().capture(
                              eventName: 'clicked_get_started',
                            );
                            Navigator.pushReplacement(
                              context,
                              MaterialPageRoute(builder: (context) => const SocialHandleScreen()),
                            );
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.white.withOpacity(0.12),
                            foregroundColor: Colors.white,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(28),
                            ),
                          ),
                          child: const Text(
                            'Get Started',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const Spacer(flex: 3),
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
