import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopSearchHeader extends StatefulWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onClearSearch;

  const DesktopSearchHeader({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.onSearchChanged,
    required this.onClearSearch,
  });

  @override
  State<DesktopSearchHeader> createState() => _DesktopSearchHeaderState();
}

class _DesktopSearchHeaderState extends State<DesktopSearchHeader> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onTextChanged);
    widget.focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onTextChanged);
    widget.focusNode.removeListener(_onFocusChanged);
    super.dispose();
  }

  void _onTextChanged() {
    setState(() {}); // Rebuild to show/hide clear button
  }

  void _onFocusChanged() {
    setState(() {}); // Rebuild to update focus styling
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);
    final isFocused = widget.focusNode.hasFocus;
    final hasText = widget.controller.text.isNotEmpty;

    return Container(
      height: responsive.responsiveHeight(
        baseHeight: 44,
        minHeight: 40,
        maxHeight: 48,
      ),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
        borderRadius: BorderRadius.circular(
          responsive.spacing(baseSpacing: 12, minSpacing: 10, maxSpacing: 14),
        ),
        border: Border.all(
          color: isFocused
              ? ResponsiveHelper.purplePrimary.withOpacity(0.6)
              : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          width: 1,
        ),
        boxShadow: isFocused
            ? [
                BoxShadow(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.04),
                  blurRadius: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 12),
                  offset: Offset(0, responsive.spacing(baseSpacing: 2, minSpacing: 1, maxSpacing: 3)),
                ),
              ]
            : null,
      ),
      child: TextField(
        controller: widget.controller,
        focusNode: widget.focusNode,
        onChanged: widget.onSearchChanged,
        style: responsive.responsiveTextStyle(
          baseFontSize: 16,
          minFontSize: 14,
          maxFontSize: 18,
          fontWeight: FontWeight.w400,
          color: ResponsiveHelper.textPrimary,
        ),
        decoration: InputDecoration(
          hintText: 'Search apps...',
          hintStyle: responsive.responsiveTextStyle(
            baseFontSize: 16,
            minFontSize: 14,
            maxFontSize: 18,
            fontWeight: FontWeight.w400,
            color: ResponsiveHelper.textQuaternary,
          ),
          border: InputBorder.none,
          contentPadding: EdgeInsets.symmetric(
            horizontal: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20),
            vertical: 0, // Remove vertical padding to align with icon
          ),
          prefixIcon: Container(
            padding: EdgeInsets.only(
              left: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20),
              right: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16),
            ),
            child: Icon(
              Icons.search_rounded,
              color: isFocused ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary,
              size: responsive.responsiveWidth(
                baseWidth: 20,
                minWidth: 18,
                maxWidth: 22,
              ),
            ),
          ),
          prefixIconConstraints: BoxConstraints(
            minWidth: responsive.responsiveWidth(baseWidth: 48, minWidth: 40, maxWidth: 56),
            maxHeight: responsive.responsiveHeight(
              baseHeight: 44,
              minHeight: 40,
              maxHeight: 48,
            ),
          ),
          suffixIcon: hasText
              ? Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: widget.onClearSearch,
                    borderRadius: BorderRadius.circular(
                      responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20),
                    ),
                    child: Container(
                      padding: EdgeInsets.all(
                        responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10),
                      ),
                      child: Icon(
                        Icons.close_rounded,
                        color: ResponsiveHelper.textTertiary,
                        size: responsive.responsiveWidth(
                          baseWidth: 18,
                          minWidth: 16,
                          maxWidth: 20,
                        ),
                      ),
                    ),
                  ),
                )
              : null,
          suffixIconConstraints: hasText
              ? BoxConstraints(
                  minWidth: responsive.responsiveWidth(baseWidth: 34, minWidth: 30, maxWidth: 38),
                  minHeight: responsive.responsiveHeight(baseHeight: 34, minHeight: 30, maxHeight: 38),
                )
              : null,
        ),
      ),
    );
  }
}
