import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopPromptTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;

  const DesktopPromptTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: MediaQuery.sizeOf(context).height * 0.1,
              maxHeight: MediaQuery.sizeOf(context).height * 0.4,
            ),
            child: Scrollbar(
              child: SingleChildScrollView(
                scrollDirection: Axis.vertical,
                reverse: false,
                child: TextFormField(
                  maxLines: null,
                  controller: controller,
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please provide a prompt';
                    }
                    return null;
                  },
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    height: 1.5,
                  ),
                  decoration: InputDecoration(
                    contentPadding: const EdgeInsets.all(16),
                    isDense: false,
                    hintText: hint,
                    hintStyle: TextStyle(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 14,
                    ),
                    border: InputBorder.none,
                    errorText: null,
                    hintMaxLines: 4,
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
