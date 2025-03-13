import 'package:flutter/material.dart';

void main() {
  runApp(const SimpleWebApp());
}

class SimpleWebApp extends StatelessWidget {
  const SimpleWebApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Omi Web',
      theme: ThemeData.dark(),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text(
              'omi',
              style: TextStyle(
                color: Colors.white,
                fontSize: 84,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.5,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'scale yourself',
              style: TextStyle(
                color: Colors.white.withOpacity(0.6),
                fontSize: 22,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 60),
            ElevatedButton(
              onPressed: () {
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
                minimumSize: const Size(300, 56),
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
            const SizedBox(height: 20),
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
      ),
    );
  }
}
