import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiMultilineInput extends AdaptiveWidget {
  final TextEditingController controller;
  final String hint;
  final int minLines;
  final int maxLines;
  final String? Function(String?)? validator;
  const OmiMultilineInput({
    super.key,
    required this.controller,
    this.hint = '',
    this.minLines = 3,
    this.maxLines = 10,
    this.validator,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base(context);

  @override
  Widget buildMobile(BuildContext context) => _base(context);

  Widget _base(BuildContext context) {
    final minHeight = 20.0 * minLines;
    final maxHeight = 20.0 * maxLines + 40;

    return Container(
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3), width: 1),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: minHeight, maxHeight: maxHeight),
        child: Scrollbar(
          child: SingleChildScrollView(
            reverse: false,
            child: TextFormField(
              controller: controller,
              maxLines: null,
              validator: validator,
              style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14, height: 1.5),
              decoration: InputDecoration(
                contentPadding: const EdgeInsets.all(16),
                hintText: hint,
                hintStyle: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 14),
                border: InputBorder.none,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
