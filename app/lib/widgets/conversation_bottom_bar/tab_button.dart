import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/widgets/conversation_bottom_bar/app_image.dart';

class TabButton extends StatelessWidget {
  final IconData? icon;
  final Widget? customIcon;
  final bool isSelected;
  final VoidCallback onTap;
  final String? label;
  final String? appImage;
  final bool isLocalAsset;
  final bool showDropdownArrow;
  final bool isLoading;
  final VoidCallback? onDropdownPressed;

  const TabButton({
    Key? key,
    this.icon,
    this.customIcon,
    required this.isSelected,
    required this.onTap,
    this.label,
    this.appImage,
    this.isLocalAsset = false,
    this.showDropdownArrow = false,
    this.isLoading = false,
    this.onDropdownPressed,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    // Calculate width based on whether we have a label and dropdown
    double buttonWidth = 60;
    if (label != null && showDropdownArrow) {
      buttonWidth = 130; // App icon + name + dropdown
    } else if (label != null) {
      buttonWidth = 100;
    }

    return Container(
      width: buttonWidth,
      height: 40,
      decoration: BoxDecoration(
        color: isSelected ? const Color(0xFF6B46C1) : Colors.transparent, // Lighter purple for selected state
        borderRadius: BorderRadius.circular(20),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: () {
            HapticFeedback.mediumImpact();
            onTap();
          }, // Always use onTap for tab selection
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (appImage != null)
                  AppImage(
                    imageUrl: appImage!,
                    isLocalAsset: isLocalAsset,
                    isLoading: isLoading,
                    size: 24,
                  )
                else if (customIcon != null)
                  SizedBox(
                    width: 24,
                    height: 24,
                    child: customIcon,
                  )
                else if (icon != null)
                  Icon(
                    icon,
                    color: isSelected ? Colors.white : Colors.grey.shade400,
                    size: 24,
                  ),
                if (label != null) ...[
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      label!.length > 12 ? '${label!.substring(0, 12)}...' : label!,
                      style: TextStyle(
                        color: isSelected ? Colors.white : Colors.grey.shade400,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                if (showDropdownArrow) ...[
                  const SizedBox(width: 2),
                  GestureDetector(
                    onTap: onDropdownPressed, // Separate tap handler for dropdown
                    child: const Icon(
                      Icons.keyboard_arrow_down,
                      color: Colors.white,
                      size: 16,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
