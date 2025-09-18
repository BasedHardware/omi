import 'package:flutter/material.dart';
import 'package:omi/gen/fonts.gen.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopWelcomeScreen extends StatelessWidget {
  final Function(String) sendMessage;
  final String? appName;

  const DesktopWelcomeScreen({
    super.key,
    required this.sendMessage,
    this.appName,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 600),
        padding: const EdgeInsets.symmetric(horizontal: 32.0, vertical: 60.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // App icon or default icon
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(40),
              ),
              child: Icon(
                Icons.chat_bubble_outline,
                size: 40,
                color: ResponsiveHelper.textPrimary.withValues(alpha: 0.8),
              ),
            ),

            const SizedBox(height: 32),

            // Welcome message
            Text(
              'How can I help?',
              style: TextStyle(
                fontFamily: FontFamily.sFProDisplay,
                fontSize: 32,
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 16),

            // Subtitle about voice interaction
            Text(
              'You can also speak to me by holding down the action button.',
              style: TextStyle(
                fontFamily: FontFamily.sFProDisplay,
                fontSize: 18,
                fontWeight: FontWeight.w400,
                color: ResponsiveHelper.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),

            const SizedBox(height: 48),
          ],
        ),
      ),
    );
  }
}
