import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/gen/assets.gen.dart';
import 'package:posthog_flutter/posthog_flutter.dart';

void main() {
  runApp(const WebApp());
}

class WebApp extends StatelessWidget {
  const WebApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Omi Web',
      theme: ThemeData(
        colorScheme: const ColorScheme.dark(
          primary: Colors.black,
          secondary: Colors.deepPurple,
          surface: Colors.black38,
        ),
      ),
      home: const WebHomePage(),
    );
  }
}

class WebHomePage extends StatelessWidget {
  const WebHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Material(
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Background color instead of image for web
          Container(
            color: Colors.black,
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
                              eventName: 'clicked_get_started_web',
                            );
                            showDialog(
                              context: context,
                              builder: (context) => AlertDialog(
                                title: const Text('Web Version'),
                                content: const Text(
                                  'This app works best on mobile devices. Please download the mobile app for the full experience.',
                                ),
                                actions: [
                                  TextButton(
                                    onPressed: () => Navigator.pop(context),
                                    child: const Text('OK'),
                                  ),
                                ],
                              ),
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
                        const SizedBox(
                          height: 24,
                        ),
                        TextButton(
                          onPressed: () {
                            showDialog(
                              context: context,
                              builder: (context) => AlertDialog(
                                title: const Text('Web Version'),
                                content: const Text(
                                  'Sign in is available in the mobile app. Please download the mobile app for the full experience.',
                                ),
                                actions: [
                                  TextButton(
                                    onPressed: () => Navigator.pop(context),
                                    child: const Text('OK'),
                                  ),
                                ],
                              ),
                            );
                          },
                          child: const Text(
                            'Sign in',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w500,
                              fontSize: 16,
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
