import 'package:flutter/material.dart';
import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class OmiSendButton extends AdaptiveWidget {
  final bool enabled;
  final VoidCallback? onPressed;

  const OmiSendButton({
    super.key,
    required this.enabled,
    required this.onPressed,
  });

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    // The outer InkWell keeps ripple consistent with other atoms.
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: enabled ? onPressed : null,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: enabled ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary.withOpacity(0.3),
            borderRadius: BorderRadius.circular(12),
            boxShadow: enabled
                ? [
                    BoxShadow(
                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                      blurRadius: 8,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : [],
          ),
          child: Icon(
            Icons.send_rounded,
            color: enabled ? Colors.white : ResponsiveHelper.textQuaternary,
            size: 18,
          ),
        ),
      ),
    );
  }
}
