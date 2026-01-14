import 'package:flutter/material.dart';

import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiConfirmDialog {
  static Future<bool?> show(
    BuildContext context, {
    required String title,
    required String message,
    String confirmLabel = 'Confirm',
    String cancelLabel = 'Cancel',
    Color confirmColor = ResponsiveHelper.errorColor,
  }) {
    return showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(
          title,
          style: const TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: Text(
          message,
          style: const TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(
              cancelLabel,
              style: const TextStyle(color: ResponsiveHelper.textSecondary),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(
              confirmLabel,
              style: TextStyle(color: confirmColor),
            ),
          ),
        ],
      ),
    );
  }

  static Future<ConfirmationResult?> showWithSkipOption(
    BuildContext context, {
    required String title,
    required String message,
    String confirmLabel = 'Confirm',
    String cancelLabel = 'Cancel',
    String skipLabel = 'Do not show this again',
    Color confirmColor = ResponsiveHelper.errorColor,
  }) {
    bool skipFutureConfirmations = false;

    return showDialog<ConfirmationResult>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          backgroundColor: ResponsiveHelper.backgroundSecondary,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(
            title,
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 18,
              fontWeight: FontWeight.w600,
            ),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                message,
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  SizedBox(
                    height: 24,
                    width: 24,
                    child: Checkbox(
                      value: skipFutureConfirmations,
                      onChanged: (value) {
                        setState(() {
                          skipFutureConfirmations = value ?? false;
                        });
                      },
                      activeColor: ResponsiveHelper.purplePrimary,
                      checkColor: ResponsiveHelper.backgroundPrimary,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      skipLabel,
                      style: const TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(
                  ctx,
                  ConfirmationResult(
                    confirmed: false,
                    skipFutureConfirmations: skipFutureConfirmations,
                  )),
              child: Text(
                cancelLabel,
                style: const TextStyle(color: ResponsiveHelper.textSecondary),
              ),
            ),
            TextButton(
              onPressed: () => Navigator.pop(
                  ctx,
                  ConfirmationResult(
                    confirmed: true,
                    skipFutureConfirmations: skipFutureConfirmations,
                  )),
              child: Text(
                confirmLabel,
                style: TextStyle(color: confirmColor),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ConfirmationResult {
  final bool confirmed;
  final bool skipFutureConfirmations;

  const ConfirmationResult({
    required this.confirmed,
    required this.skipFutureConfirmations,
  });
}
