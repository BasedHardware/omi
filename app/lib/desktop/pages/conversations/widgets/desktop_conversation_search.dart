import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopConversationSearch extends StatefulWidget {
  final TextEditingController controller;
  final Function(String) onSearchChanged;

  const DesktopConversationSearch({
    super.key,
    required this.controller,
    required this.onSearchChanged,
  });

  @override
  State<DesktopConversationSearch> createState() => _DesktopConversationSearchState();
}

class _DesktopConversationSearchState extends State<DesktopConversationSearch> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;
  final FocusNode _focusNode = FocusNode();
  bool _isFocused = false;

  @override
  void initState() {
    super.initState();

    _animationController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );

    _scaleAnimation = Tween<double>(begin: 1.0, end: 1.02).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeInOut),
    );

    _focusNode.addListener(() {
      setState(() {
        _isFocused = _focusNode.hasFocus;
      });

      if (_isFocused) {
        _animationController.forward();
      } else {
        _animationController.reverse();
      }
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return ScaleTransition(
      scale: _scaleAnimation,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: responsive.maxContainerWidth(baseMaxWidth: 600),
        ),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _isFocused ? ResponsiveHelper.purplePrimary.withOpacity(0.6) : ResponsiveHelper.backgroundTertiary,
            width: 1,
          ),
          boxShadow: _isFocused
              ? [
                  BoxShadow(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: TextField(
          controller: widget.controller,
          focusNode: _focusNode,
          onChanged: widget.onSearchChanged,
          style: TextStyle(
            fontSize: responsive.responsiveFontSize(baseFontSize: 16),
            fontWeight: FontWeight.w500,
            color: ResponsiveHelper.textPrimary,
            height: 1.4,
          ),
          decoration: InputDecoration(
            hintText: 'Search conversations...',
            hintStyle: TextStyle(
              fontSize: responsive.responsiveFontSize(baseFontSize: 16),
              color: ResponsiveHelper.textQuaternary,
              fontWeight: FontWeight.w400,
            ),
            prefixIcon: Container(
              width: 24,
              height: 24,
              margin: const EdgeInsets.only(left: 20, right: 16),
              child: Center(
                child: Icon(
                  Icons.search_rounded,
                  color: _isFocused ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
                  size: responsive.iconSize(baseSize: 20),
                ),
              ),
            ),
            suffixIcon: widget.controller.text.isNotEmpty
                ? Container(
                    width: 24,
                    height: 24,
                    margin: const EdgeInsets.only(right: 16),
                    child: Center(
                      child: Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            widget.controller.clear();
                            widget.onSearchChanged('');
                          },
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            width: 24,
                            height: 24,
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.backgroundTertiary,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(
                              Icons.close_rounded,
                              color: ResponsiveHelper.textTertiary,
                              size: responsive.iconSize(baseSize: 14),
                            ),
                          ),
                        ),
                      ),
                    ),
                  )
                : null,
            border: InputBorder.none,
            contentPadding: EdgeInsets.symmetric(
              horizontal: responsive.spacing(baseSpacing: 20),
              vertical: responsive.spacing(baseSpacing: 18),
            ),
          ),
        ),
      ),
    );
  }
}
