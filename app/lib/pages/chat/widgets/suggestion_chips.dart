import 'package:flutter/material.dart';
import 'package:omi/gen/fonts.gen.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class SuggestionChips extends StatelessWidget {
  final Function(String) sendMessage;

  const SuggestionChips({
    super.key,
    required this.sendMessage,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 70,
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16.0),
        children: [
          _buildSuggestedAction(
            'Search my history for anything',
            () => sendMessage('Search my history for anything'),
          ),
          const SizedBox(width: 8),
          _buildSuggestedAction(
            'Summarize priorities from this past week',
            () => sendMessage('Summarize priorities from this past week'),
          ),
          const SizedBox(width: 8),
          _buildSuggestedAction(
            'How are you as a person?',
            () => sendMessage('How are you as a person?'),
          ),
          const SizedBox(width: 16), // Extra padding at the end
        ],
      ),
    );
  }

  Widget _buildSuggestedAction(String text, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20.0),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16),
          decoration: BoxDecoration(
            color: Color(0xFF1f1f25),
            borderRadius: BorderRadius.circular(20.0),
            border: Border.all(
              color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.2),
              width: 1,
            ),
          ),
          child: Text(
            text,
            style: TextStyle(
              fontFamily: FontFamily.sFProDisplay,
              fontSize: 16,
              fontWeight: FontWeight.w400,
              color: ResponsiveHelper.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
