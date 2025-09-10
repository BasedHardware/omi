import 'package:flutter/material.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/gen/fonts.gen.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class WelcomeScreen extends StatelessWidget {
  final Function(String) sendMessage;
  final String? appName;

  const WelcomeScreen({
    super.key,
    required this.sendMessage,
    this.appName,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 40.0),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // App icon or default icon
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(32),
            ),
            child: Icon(
              Icons.chat_bubble_outline,
              size: 32,
              color: ResponsiveHelper.textPrimary.withValues(alpha: 0.8),
            ),
          ),

          const SizedBox(height: 24),

          // Welcome message
          Text(
            'How can I help?',
            style: TextStyle(
              fontFamily: FontFamily.sFProDisplay,
              fontSize: 28,
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 12),

          // Subtitle about voice interaction
          Text(
            'You can also speak to me by holding down the action button.',
            style: TextStyle(
              fontFamily: FontFamily.sFProDisplay,
              fontSize: 16,
              fontWeight: FontWeight.w400,
              color: ResponsiveHelper.textSecondary,
            ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 40),

          // Suggested action buttons
          _buildSuggestedAction(
            'Search my history for anything',
            () => sendMessage('Search my history for anything'),
          ),

          const SizedBox(height: 12),

          _buildSuggestedAction(
            'Summarize priorities from this past week',
            () => sendMessage('Summarize priorities from this past week'),
          ),

          const SizedBox(height: 12),

          _buildSuggestedAction(
            'How can I improve my daily routine?',
            () => sendMessage('How can I improve my daily routine?'),
          ),
        ],
      ),
    );
  }

  Widget _buildSuggestedAction(String text, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 14.0),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(12.0),
          border: Border.all(
            color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontFamily: FontFamily.sFProDisplay,
            fontSize: 15,
            fontWeight: FontWeight.w400,
            color: ResponsiveHelper.textPrimary,
          ),
          textAlign: TextAlign.start,
        ),
      ),
    );
  }
}
