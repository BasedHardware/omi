import 'package:flutter/material.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/desktop/desktop_app.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Route to appropriate app tree based on screen width
        if (constraints.maxWidth >= 1100) {
          return const DesktopApp(); // Desktop app tree
        } else {
          return const MobileApp(); // Mobile app tree (existing)
        }
      },
    );
  }
}
