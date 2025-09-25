import 'package:flutter/material.dart';
import 'package:omi/utils/platform/floating_chat_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class FloatingWindowSettings extends StatelessWidget {
  const FloatingWindowSettings({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Reset Window Positions',
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Restore the floating button and chat window to their default positions.',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              ElevatedButton(
                onPressed: () {
                  FloatingChatService.resetAllPositions();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: const Text('Window positions have been reset.'),
                      backgroundColor: ResponsiveHelper.backgroundTertiary,
                      behavior: SnackBarBehavior.floating,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      duration: const Duration(seconds: 2),
                    ),
                  );
                },
                child: const Text('Reset'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
