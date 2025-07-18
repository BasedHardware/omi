import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiMessageInput extends AdaptiveWidget {
  final TextEditingController controller;
  final String hint;
  final EdgeInsetsGeometry? margin;
  final double maxHeight;

  const OmiMessageInput({
    super.key,
    required this.controller,
    this.hint = '💬 Type your message...',
    this.margin,
    this.maxHeight = 120,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    return Container(
      margin: margin ?? const EdgeInsets.symmetric(horizontal: 8),
      constraints: BoxConstraints(maxHeight: maxHeight),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.8),
        borderRadius: BorderRadius.circular(16),
      ),
      child: TextField(
        controller: controller,
        maxLines: null,
        keyboardType: TextInputType.multiline,
        style: const TextStyle(
          fontSize: 14,
          color: ResponsiveHelper.textPrimary,
          height: 1.4,
        ),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(
            fontSize: 14,
            color: ResponsiveHelper.textTertiary,
          ),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        ),
      ),
    );
  }
}
