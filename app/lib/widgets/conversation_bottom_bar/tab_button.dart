import 'package:flutter/material.dart';
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
    return Container(
      width: label != null ? 120 : 80,
      height: 40,
      decoration: BoxDecoration(
        color: isSelected ? Colors.deepPurple.withOpacity(0.3) : Colors.transparent,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: showDropdownArrow ? onDropdownPressed : onTap,
          child: Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (customIcon != null)
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
                  )
                else if (appImage != null)
                  AppImage(
                    imageUrl: appImage!,
                    isLocalAsset: isLocalAsset,
                    isLoading: isLoading,
                    size: 24,
                  ),
                if (label != null) ...[
                  const SizedBox(width: 4),
                  Flexible(
                    child: Container(
                      width: 60,
                      child: ShaderMask(
                        shaderCallback: (Rect bounds) {
                          return LinearGradient(
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                            colors: [Colors.white, Colors.transparent],
                            stops: [0.8, 1.0],
                          ).createShader(bounds);
                        },
                        blendMode: BlendMode.dstIn,
                        child: Text(
                          label ?? '',
                          style: TextStyle(
                            color: isSelected ? Colors.white : Colors.grey.shade400,
                            fontSize: 12,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                  ),
                ],
                if (showDropdownArrow) ...[
                  const SizedBox(width: 2),
                  Icon(
                    Icons.keyboard_arrow_down,
                    color: Colors.white,
                    size: 16,
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
