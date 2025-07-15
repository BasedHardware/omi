import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSearchInput extends AdaptiveWidget {
  final TextEditingController controller;
  final FocusNode? focusNode;
  final ValueChanged<String>? onChanged;
  final VoidCallback? onClear;
  final String hint;
  const OmiSearchInput({
    super.key,
    required this.controller,
    this.focusNode,
    this.onChanged,
    this.onClear,
    this.hint = 'Search...',
  });

  @override
  Widget buildDesktop(BuildContext context) {
    return _base(context);
  }

  @override
  Widget buildMobile(BuildContext context) {
    return _base(context);
  }

  Widget _base(BuildContext context) {
    return _AdaptiveSearchInner(
      controller: controller,
      focusNode: focusNode,
      hint: hint,
      onChanged: onChanged,
      onClear: onClear,
    );
  }
}

class _AdaptiveSearchInner extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode? focusNode;
  final String hint;
  final ValueChanged<String>? onChanged;
  final VoidCallback? onClear;

  const _AdaptiveSearchInner({
    required this.controller,
    this.focusNode,
    required this.hint,
    this.onChanged,
    this.onClear,
  });

  @override
  State<_AdaptiveSearchInner> createState() => _AdaptiveSearchInnerState();
}

class _AdaptiveSearchInnerState extends State<_AdaptiveSearchInner> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onTextChanged);
    widget.focusNode?.addListener(_onTextChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onTextChanged);
    widget.focusNode?.removeListener(_onTextChanged);
    super.dispose();
  }

  void _onTextChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final isFocused = widget.focusNode?.hasFocus ?? false;
    final hasText = widget.controller.text.isNotEmpty;

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
        onChanged: widget.onChanged,
        style: const TextStyle(
          color: ResponsiveHelper.textPrimary,
          fontSize: 14,
        ),
        decoration: InputDecoration(
          prefixIcon: const Icon(Icons.search_rounded, color: ResponsiveHelper.textQuaternary, size: 20),
          hintText: widget.hint,
          hintStyle: const TextStyle(
            color: ResponsiveHelper.textTertiary,
            fontSize: 14,
          ),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 12),
          suffixIcon: hasText
              ? InkWell(
                  onTap: () {
                    widget.onClear?.call();
                    setState(() {});
                  },
                  borderRadius: BorderRadius.circular(12),
                  child: const Icon(Icons.close_rounded, size: 18, color: ResponsiveHelper.textTertiary),
                )
              : null,
        ),
      ),
    );
  }
}
