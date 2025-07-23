import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiTextInput extends AdaptiveWidget {
  final TextEditingController controller;
  final FocusNode? focusNode;
  final String hint;
  final bool obscureText;
  final ValueChanged<String>? onChanged;
  final TextInputType? keyboardType;
  final int? maxLength;

  const OmiTextInput({
    super.key,
    required this.controller,
    this.focusNode,
    this.hint = '',
    this.obscureText = false,
    this.onChanged,
    this.keyboardType,
    this.maxLength,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    return _TextInputInner(
      controller: controller,
      focusNode: focusNode,
      hint: hint,
      obscureText: obscureText,
      onChanged: onChanged,
      keyboardType: keyboardType,
      maxLength: maxLength,
    );
  }
}

class _TextInputInner extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode? focusNode;
  final String hint;
  final bool obscureText;
  final ValueChanged<String>? onChanged;
  final TextInputType? keyboardType;
  final int? maxLength;

  const _TextInputInner({
    required this.controller,
    this.focusNode,
    required this.hint,
    required this.obscureText,
    this.onChanged,
    this.keyboardType,
    this.maxLength,
  });

  @override
  State<_TextInputInner> createState() => _TextInputInnerState();
}

class _TextInputInnerState extends State<_TextInputInner> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChange);
    widget.focusNode?.addListener(_onChange);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChange);
    widget.focusNode?.removeListener(_onChange);
    super.dispose();
  }

  void _onChange() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final isFocused = widget.focusNode?.hasFocus ?? false;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      height: 44,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isFocused
              ? ResponsiveHelper.purplePrimary.withOpacity(0.6)
              : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          width: 1,
        ),
      ),
      child: TextField(
        controller: widget.controller,
        focusNode: widget.focusNode,
        obscureText: widget.obscureText,
        onChanged: widget.onChanged,
        keyboardType: widget.keyboardType,
        maxLength: widget.maxLength,
        style: const TextStyle(
          color: ResponsiveHelper.textPrimary,
          fontSize: 14,
        ),
        decoration: InputDecoration(
          counterText: '',
          hintText: widget.hint,
          hintStyle: const TextStyle(
            color: ResponsiveHelper.textTertiary,
            fontSize: 14,
          ),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        ),
      ),
    );
  }
}
