import 'package:flutter/material.dart';
import 'package:omi/ui/atoms/omi_multiline_input.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiEditDialog {
  static Future<String?> show(
    BuildContext context, {
    required String title,
    required String subtitle,
    required String currentValue,
    required IconData icon,
    Color iconColor = ResponsiveHelper.warningColor,
    String fieldLabel = 'Value',
    String fieldHint = 'Enter value...',
    String confirmLabel = 'Save Changes',
    String cancelLabel = 'Cancel',
    int maxLines = 2,
  }) {
    final TextEditingController controller = TextEditingController(text: currentValue);

    return showDialog<String>(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.7),
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          width: 480,
          padding: const EdgeInsets.all(28),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 24,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: iconColor.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      icon,
                      size: 24,
                      color: iconColor,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w600,
                            color: ResponsiveHelper.textPrimary,
                          ),
                        ),
                        Text(
                          subtitle,
                          style: const TextStyle(
                            fontSize: 14,
                            color: ResponsiveHelper.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 24),

              // Field label
              Text(
                fieldLabel,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: ResponsiveHelper.textPrimary,
                ),
              ),
              const SizedBox(height: 8),

              // Input field using OmiMultilineInput
              OmiMultilineInput(
                controller: controller,
                hint: fieldHint,
                minLines: 1,
                maxLines: maxLines,
              ),

              const SizedBox(height: 28),

              // Buttons
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 48,
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(ctx).pop(),
                        style: OutlinedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          foregroundColor: ResponsiveHelper.textSecondary,
                          side: const BorderSide(
                            color: ResponsiveHelper.backgroundTertiary,
                            width: 1,
                          ),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 16),
                        ),
                        child: Text(
                          cancelLabel,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: SizedBox(
                      height: 48,
                      child: ElevatedButton(
                        onPressed: () {
                          final newValue = controller.text.trim();
                          if (newValue.isNotEmpty && newValue != currentValue) {
                            Navigator.of(ctx).pop(newValue);
                          } else {
                            Navigator.of(ctx).pop();
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: ResponsiveHelper.purplePrimary,
                          foregroundColor: Colors.white,
                          elevation: 0,
                          shadowColor: Colors.transparent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 16),
                        ),
                        child: Text(
                          confirmLabel,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
